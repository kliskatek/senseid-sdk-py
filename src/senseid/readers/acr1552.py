import logging
import threading
from typing import List, Callable, Optional

from driver_snfc_py_acr1552.acr1552 import Acr1552

from . import SenseidReader, SenseidReaderDetails, SenseidReaderMode, SenseidReaderError
from ..parsers import SenseidTag
from ..parsers.nfc import convert_to_uint, Endianness, parse_nfc_ndef, parse_nfc_bulk_sample
from ..parsers.nfc.yaml import SENSEID_NFC_DEF

logger = logging.getLogger(__name__)


class SenseidAcr1552(SenseidReader):

    NTAG5_NDEF_BASE_BLOCK = 0
    NTAG5_NDEF_HEADER_NBLOCKS = 2

    NTAG5_IDX_BLOCK = 50
    NTAG5_IDX_NBLOCKS = 1

    NTAG5_DATA_BASE_BLOCK = 0
    NTAG5_DATA_NBLOCKS = 50

    MAX_RECONNECT_ATTEMPTS = 3

    def __init__(self):
        self.driver = Acr1552()
        self.details: SenseidReaderDetails | None = None
        self._connection_string: str | None = None
        self._mode: SenseidReaderMode = SenseidReaderMode.NDEF
        self._is_polling: bool = False
        self._poll_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._notification_callback: Callable[[SenseidTag], None] | None = None
        self._error_callback: Callable[[SenseidReaderError], None] | None = None
        # Type detected from NDEF read, used by BULK parser
        self._detected_type_id: int | None = None
        # Bulk state
        self._last_bulk_index: int | None = None
        self._last_uid = None

    def connect(self, connection_string: str):
        try:
            self._connection_string = connection_string
            result = self.driver.connect(connection_string=connection_string)
            if result:
                self.driver.set_power(True)
                self.driver.change_fw_mode(False)  # NDEF mode
                self._mode = SenseidReaderMode.NDEF
            return result
        except Exception as e:
            logger.error(f'ACR1552 connect error: {e}')
            return False

    def disconnect(self):
        self._stop_polling()
        try:
            self.driver.set_power(True)  # Field ON so reconnect works later
            self.driver.disconnect()
        except Exception:
            pass

    def get_details(self) -> SenseidReaderDetails:
        if self.details is None:
            self.details = SenseidReaderDetails(
                model_name='ACR1552',
                region='EU',
                firmware_version='1.0.1',
                antenna_count=1,
                min_tx_power=0,
                max_tx_power=0
            )
        return self.details

    def get_tx_power(self) -> float:
        return 0

    def set_tx_power(self, dbm: float):
        pass  # NFC reader has no adjustable TX power

    def get_antenna_config(self) -> List[bool]:
        return [True]

    def set_antenna_config(self, antenna_config_array: List[bool]):
        pass  # NFC reader has a single fixed antenna

    # -- Mode methods --

    def get_supported_modes(self) -> List[SenseidReaderMode]:
        return [SenseidReaderMode.NDEF, SenseidReaderMode.BULK]

    def get_mode(self) -> SenseidReaderMode:
        return self._mode

    def set_mode(self, mode: SenseidReaderMode):
        supported = self.get_supported_modes()
        if mode not in supported:
            raise ValueError(f'Mode {mode} not supported. Supported: {supported}')

        was_polling = self._is_polling
        if was_polling:
            self._stop_polling()

        if mode == SenseidReaderMode.NDEF:
            self.driver.change_fw_mode(False)
        elif mode == SenseidReaderMode.BULK:
            self.driver.change_fw_mode(True)
            self._last_bulk_index = None
            self._last_uid = None

        self._mode = mode

        if was_polling:
            self._start_polling()

    # -- Inventory (unified interface) --

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None],
                              error_callback: Optional[Callable[[SenseidReaderError], None]] = None):
        self._notification_callback = notification_callback
        self._error_callback = error_callback
        self._start_polling()

    def stop_inventory_async(self):
        self._stop_polling()

    # -- Internal polling --

    def _start_polling(self):
        self._stop_event.clear()
        self._is_polling = True
        if self._mode == SenseidReaderMode.NDEF:
            self._poll_thread = threading.Thread(target=self._ndef_loop, daemon=True)
        else:
            self._poll_thread = threading.Thread(target=self._bulk_loop, daemon=True)
        self._poll_thread.start()

    def _stop_polling(self):
        if not self._is_polling:
            return
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=3.0)
        self._poll_thread = None
        self._is_polling = False

    def _ndef_loop(self):
        while not self._stop_event.is_set():
            try:
                uid = self.driver.get_uid()
                if uid is not None:
                    tag = self._read_and_parse_ndef(uid)
                    if tag is not None and self._notification_callback:
                        self._notification_callback(tag)
                else:
                    logger.warning('NFC NDEF: no tag detected')
                    self._handle_error('TAG_LOST')
                    return
            except Exception as e:
                logger.error(f'NFC NDEF poll error: {e}')
                self._handle_error('TAG_LOST')
                return
            self._stop_event.wait(0.5)

    def _bulk_loop(self):
        consecutive_failures = 0
        while not self._stop_event.is_set():
            try:
                uid = self.driver.get_uid()
                if uid is not None:
                    consecutive_failures = 0

                    # New tag detected - switch it to bulk mode
                    if uid != self._last_uid:
                        self._last_uid = uid
                        self.driver.change_fw_mode(True)
                        self._last_bulk_index = None
                        self._stop_event.wait(0.2)
                        continue

                    current_index = self._read_tag_index()
                    if current_index is not None and current_index != self._last_bulk_index:
                        raw_data = self.driver.read_data(self.NTAG5_DATA_BASE_BLOCK, self.NTAG5_DATA_NBLOCKS)
                        if raw_data is not None:
                            # NDEF data guard: check if data is still NDEF
                            if len(raw_data) >= 2 and raw_data[0] == 0xE1 and raw_data[1] == 0x40:
                                self.driver.change_fw_mode(True)
                                self._stop_event.wait(0.2)
                                continue

                            raw_values = convert_to_uint(raw_data, 2, Endianness.LITTLE.value)
                            if raw_values:
                                self._last_bulk_index = current_index
                                self._emit_bulk_samples(raw_values, uid)
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= 10:
                        logger.warning('NFC BULK: tag lost (consecutive failures)')
                        self._handle_error('TAG_LOST')
                        return
            except Exception as e:
                logger.error(f'NFC BULK poll error: {e}')
                self._handle_error('TAG_LOST')
                return
            self._stop_event.wait(0.02)

    # -- Helpers --

    def _read_and_parse_ndef(self, uid) -> Optional[SenseidTag]:
        """Read NDEF data from tag and parse into SenseidTag."""
        header = self.driver.read_data(self.NTAG5_NDEF_BASE_BLOCK, self.NTAG5_NDEF_HEADER_NBLOCKS)
        if header is None or len(header) < 6:
            return None
        if header[0] != 0xE1 or header[1] != 0x40 or header[4] != 0x03:
            return None

        ndef_length = header[5]
        total_bytes = 4 + 1 + 1 + ndef_length
        total_blocks = (total_bytes + 3) // 4

        data = self.driver.read_data(self.NTAG5_NDEF_BASE_BLOCK, total_blocks)
        if data is None:
            return None

        uid_str = bytearray(uid).hex().upper() if uid else None
        tag, type_id = parse_nfc_ndef(bytearray(data), uid=uid_str)

        if type_id is not None:
            self._detected_type_id = type_id

        return tag

    def _read_tag_index(self) -> Optional[int]:
        """Read the current write index from the tag."""
        data = self.driver.read_data(self.NTAG5_IDX_BLOCK, self.NTAG5_IDX_NBLOCKS)
        idx_list = convert_to_uint(data, 4, Endianness.LITTLE.value)
        if idx_list:
            return idx_list[0]
        return None

    def _emit_bulk_samples(self, raw_values: list, uid):
        """Group raw uint16 values by data_def size and emit one SenseidTag per sample."""
        type_id = self._detected_type_id or SENSEID_NFC_DEF.default_type
        type_def = SENSEID_NFC_DEF.types.get(type_id)
        if type_def is None:
            return

        group_size = len(type_def.data_def)
        uid_str = bytearray(uid).hex().upper() if uid else None

        for sample_idx in range(0, len(raw_values) // group_size):
            start = sample_idx * group_size
            group = raw_values[start:start + group_size]
            tag = parse_nfc_bulk_sample(group, sample_idx, type_id, uid=uid_str)
            if tag is not None and self._notification_callback:
                self._notification_callback(tag)

    def _handle_error(self, error_type: str):
        """Handle tag loss: try auto-reconnect, emit error if all retries fail."""
        self._stop_event.set()
        self._poll_thread = None
        self._is_polling = False

        try:
            self.driver.disconnect()
        except Exception:
            pass

        # Auto-reconnect attempts
        for attempt in range(1, self.MAX_RECONNECT_ATTEMPTS + 1):
            try:
                logger.info(f'NFC reconnect attempt {attempt}/{self.MAX_RECONNECT_ATTEMPTS}')
                result = self.driver.connect(connection_string=self._connection_string)
                if result:
                    self.driver.set_power(True)
                    # Restore mode
                    if self._mode == SenseidReaderMode.BULK:
                        self.driver.change_fw_mode(True)
                        self._last_bulk_index = None
                        self._last_uid = None
                    else:
                        self.driver.change_fw_mode(False)
                    # Restart polling
                    self._start_polling()
                    logger.info(f'NFC reconnected on attempt {attempt}')
                    return
            except Exception as e:
                logger.warning(f'NFC reconnect attempt {attempt} failed: {e}')

        # All retries exhausted
        logger.error(f'NFC reconnect failed after {self.MAX_RECONNECT_ATTEMPTS} attempts')
        if self._error_callback:
            self._error_callback(SenseidReaderError(error_type, 'Tag lost, reconnect failed'))
