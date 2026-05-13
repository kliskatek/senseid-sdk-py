import logging
import threading
import time
from typing import List, Callable, Optional

from redrcp import RedRcp, NotificationTpeCuiii, NotificationTpeCuiiiRssi, NotificationTpeCuiiiTid, ParamMemory

from ..parsers import SenseidTag
from ..parsers.farsens import SenseidFarsensTag
from ..parsers.farsens.yaml import SENSEID_FARSENS_DEF
from ..parsers.legacy import SenseidLegacyTag
from ..parsers.legacy.yaml import SENSEID_LEGACY_DEF
from ..parsers.rain import SenseidRainTag
from ..readers import SenseidReader, SenseidReaderDetails, SenseidReaderMode

logger = logging.getLogger(__name__)


LEGACY_OP_PERIOD_S = 0.1          # min interval between consecutive operations
LEGACY_INVENTORY_WINDOW_S = 0.08  # how long the inventory op holds the air
LEGACY_USER_WORD_PTR = 0x100


class SenseidReaderRedRcp(SenseidReader):

    def __init__(self):
        self.driver = RedRcp()
        self.notification_callback = None
        self.details = None
        self._mode: SenseidReaderMode = SenseidReaderMode.SENSEID
        # LEGACY loop state
        self._legacy_thread: Optional[threading.Thread] = None
        self._legacy_stop = threading.Event()
        self._legacy_word_count: int = 0
        self._legacy_seen_lock = threading.Lock()
        self._legacy_seen: set[str] = set()

    def connect(self, connection_string: str):
        if not self.driver.connect(connection_string=connection_string):
            return False
        self.driver.set_notification_callback(self._redrcp_notification_callback)
        # NOTE: set_anti_collision_mode / set_query_parameters here used to
        # leave RED4S_v2.2.1_K firmware unable to inventory afterwards. The
        # values stored in the reader's NVM work fine, so we don't override.
        return True

    @staticmethod
    def _epc_starts_with(epc_hex: str, prefix: bytes) -> bool:
        try:
            epc_bytes = bytes.fromhex(epc_hex)
        except (ValueError, TypeError):
            return False
        return epc_bytes[:len(prefix)] == prefix

    def _emit_tag(self, epc_hex: str, user_mem_hex: Optional[str]):
        if self.notification_callback is None:
            return
        if self._epc_starts_with(epc_hex, bytes(SENSEID_FARSENS_DEF.pen_header)):
            tag = SenseidFarsensTag(epc=epc_hex, user_mem_hex=user_mem_hex)
        elif self._epc_starts_with(epc_hex, bytes(SENSEID_LEGACY_DEF.pen_header)):
            tag = SenseidLegacyTag(epc=epc_hex, user_mem_hex=user_mem_hex)
        else:
            tag = SenseidRainTag(epc=epc_hex)
        self.notification_callback(tag)

    def _redrcp_notification_callback(self, notif: NotificationTpeCuiii
                                                | NotificationTpeCuiiiRssi
                                                | NotificationTpeCuiiiTid):
        try:
            epc_hex = bytes(notif.epc).hex().upper()
        except Exception:
            return
        if self._mode == SenseidReaderMode.LEGACY:
            # Accumulate EPCs seen during the current inventory window; the
            # legacy loop will perform the explicit Read on each of them.
            with self._legacy_seen_lock:
                self._legacy_seen.add(epc_hex)
        else:
            self._emit_tag(epc_hex, user_mem_hex=None)

    # ── Modes ─────────────────────────────────

    def get_supported_modes(self) -> List[SenseidReaderMode]:
        return [SenseidReaderMode.SENSEID, SenseidReaderMode.LEGACY]

    def get_mode(self) -> SenseidReaderMode:
        return self._mode

    def set_mode(self, mode: SenseidReaderMode):
        super().set_mode(mode)
        self._mode = mode
        if mode == SenseidReaderMode.LEGACY:
            self._legacy_word_count = max(SENSEID_LEGACY_DEF.word_count,
                                          SENSEID_FARSENS_DEF.word_count)
            logger.info('Reader mode set to LEGACY (USER@0x%X, %d words)',
                        LEGACY_USER_WORD_PTR, self._legacy_word_count)
        else:
            logger.info('Reader mode set to %s', mode.value)

    # ── Inventory ─────────────────────────────

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None],
                              error_callback=None):
        self.notification_callback = notification_callback
        if self._mode == SenseidReaderMode.LEGACY:
            self._legacy_stop.clear()
            self._legacy_thread = threading.Thread(
                target=self._legacy_loop, daemon=True, name='RedRcpLegacyLoop')
            self._legacy_thread.start()
            return None
        return self.driver.start_auto_read2()

    def stop_inventory_async(self):
        if self._legacy_thread is not None:
            self._legacy_stop.set()
            self._legacy_thread.join(timeout=2)
            self._legacy_thread = None
            return None
        if self.driver.is_connected():
            return self.driver.stop_auto_read2()
        return None

    def _is_legacy_or_farsens(self, epc_hex: str) -> bool:
        return (self._epc_starts_with(epc_hex, bytes(SENSEID_LEGACY_DEF.pen_header))
                or self._epc_starts_with(epc_hex, bytes(SENSEID_FARSENS_DEF.pen_header)))

    def _legacy_loop(self):
        """CW on continuously. Every LEGACY_OP_PERIOD_S we run one
        operation from a rotating list:
          [inventory, read sensor_tag_1, read sensor_tag_2, ...]

        - "inventory" refreshes the list of sensor EPCs (legacy / Farsens).
        - "read"  performs a user-memory Read of one sensor tag.

        Non-sensor tags are emitted once per inventory pass as plain
        Rain ID (no Read attempted on them — would just burn the
        driver's 3 s timeout)."""
        sensor_epcs: list[str] = []
        seen_passthrough: set[str] = set()

        def do_inventory():
            with self._legacy_seen_lock:
                self._legacy_seen.clear()
            try:
                self.driver.start_auto_read2()
            except Exception as e:
                logger.error('legacy_loop start_auto_read2 failed: %s', e)
                return
            self._legacy_stop.wait(LEGACY_INVENTORY_WINDOW_S)
            try:
                self.driver.stop_auto_read2()
            except Exception:
                pass
            with self._legacy_seen_lock:
                seen = set(self._legacy_seen)
            new_sensor = [e for e in seen if self._is_legacy_or_farsens(e)]
            # Preserve the rotation order; append newcomers, drop strays.
            sensor_epcs[:] = [e for e in sensor_epcs if e in new_sensor] + \
                             [e for e in new_sensor if e not in sensor_epcs]
            for epc in seen - set(sensor_epcs):
                if epc not in seen_passthrough:
                    seen_passthrough.add(epc)
                    self._emit_tag(epc, None)

        def do_read(epc_hex: str):
            user_mem = None
            try:
                data = self.driver.read(epc_hex, ParamMemory.USER,
                                        LEGACY_USER_WORD_PTR,
                                        self._legacy_word_count)
                if data:
                    user_mem = bytes(data).hex().upper()
            except Exception as e:
                logger.debug('legacy_loop read(%s) failed: %s', epc_hex, e)
            self._emit_tag(epc_hex, user_mem)

        try:
            try:
                self.driver.set_cw(True)
            except Exception:
                pass
            op_idx = 0
            while not self._legacy_stop.is_set():
                op_start = time.monotonic()
                # Rotating ops: index 0 = inventory, 1..N = sensor reads.
                ops_len = 1 + len(sensor_epcs)
                op = op_idx % ops_len
                op_idx += 1
                if op == 0:
                    do_inventory()
                else:
                    do_read(sensor_epcs[op - 1])
                # Pace to LEGACY_OP_PERIOD_S between op starts.
                elapsed = time.monotonic() - op_start
                remaining = LEGACY_OP_PERIOD_S - elapsed
                if remaining > 0:
                    self._legacy_stop.wait(remaining)
        finally:
            try:
                self.driver.set_cw(False)
            except Exception:
                pass

    # ── Reader info / config ──────────────────

    def disconnect(self):
        self.driver.disconnect()

    def get_details(self):
        info_model = self.driver.get_info_model()
        info_fw_version = self.driver.get_info_fw_version()
        info_detail = self.driver.get_info_detail()
        self.details = SenseidReaderDetails(
            model_name=info_model,
            region=info_detail.region.name,
            firmware_version=info_fw_version,
            antenna_count=1,
            min_tx_power=info_detail.min_tx_power,
            max_tx_power=info_detail.max_tx_power,
            technology=self.technology,
        )
        return self.details

    def get_tx_power(self):
        return self.driver.get_tx_power()

    def set_tx_power(self, dbm):
        if self.details is None:
            self.get_details()
        if dbm > self.details.max_tx_power:
            dbm = self.details.max_tx_power
            logger.warning('Power set to max power: ' + str(dbm))
        if dbm < self.details.min_tx_power:
            dbm = self.details.min_tx_power
            logger.warning('Power set to min power: ' + str(dbm))
        self.driver.set_tx_power(dbm=dbm)

    def get_antenna_config(self):
        return [True]

    def set_antenna_config(self, antenna_config_array: List[bool]):
        pass
