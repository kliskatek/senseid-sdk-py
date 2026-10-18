import logging
import threading
from typing import List, Callable, Optional

from nurapy import NurAPY, NurTagDataMeta, InventoryStreamNotification, ModuleSetupFlags, ModuleSetup, NurDeviceCaps
from nurapy.protocol.command.inv_read_config import IrBank, IrType
from nurapy.protocol.command.module_setup import (ModuleSetupLinkFreq,
                                                  ModuleSetupRxDec,
                                                  ModuleSetupInvTarget,
                                                  ModuleSetupPowerSave)

from . import SenseidReader, SenseidReaderDetails, SenseidReaderError, SenseidReaderMode
from ..parsers import SenseidTag
from ..parsers.farsens import SenseidFarsensTag
from ..parsers.farsens.yaml import SENSEID_FARSENS_DEF
from ..parsers.senseread import SenseidSenseReadTag, is_senseid_senseread_epc
from ..parsers.senseread.yaml import SENSEID_SENSEREAD_DEF
from ..parsers.rain import SenseidRainTag

logger = logging.getLogger(__name__)

# Sessions used by the inventory stream.
#
# Plain inventory (SENSEID mode, and the plain phase of SENSEREAD): session 0.
# SenseID tags reset their flag on every measurement and passive ID tags on
# every power loss, so S0 reads both as fast as they can answer.
#
# Embedded-read phase of SENSEREAD: session 1. senseRead tags stay powered, so
# their S0 flag never goes back to A: in S0 they are read once and then go
# silent. The dual target (AB) does not save them on the STIX, because the
# module only switches to B after a round with no tags and a SenseID tag in
# the field answers every round. S1 brings them back to A after ~0.5 s.
# Each session has its own flag, so the S0 phase does not spend the S1 one.
SESSION_PLAIN = 0
SESSION_IR = 1

# SENSEREAD alternates two phases, because a STIX inventory with embedded read
# only reports the tags that answer the read: SenseID tags (inventory only) and
# ID tags without User memory at 0x100 drop out of it. The carrier stays on
# through the switch (~50 ms), so SenseID tags keep harvesting during the
# embedded-read phase. The embedded-read phase has to outlast the S1
# persistence (~0.56 s measured) to catch each senseRead tag at least once.
SENSEREAD_IR_PHASE_S = 1.6
SENSEREAD_PLAIN_PHASE_S = 0.6


class SenseidNurapy(SenseidReader):

    def __init__(self):
        self.driver = NurAPY()
        self.notification_callback = None
        self.error_callback = None
        self.device_caps: NurDeviceCaps | None = None
        self.details = None
        self._mode: SenseidReaderMode = SenseidReaderMode.SENSEID
        # Serialises driver commands between the phase thread and the
        # notification callback (stream restarts, clear_notified_tags).
        self._lock = threading.RLock()
        self._running = False
        self._switching = False
        self._ir_active = False
        self._phase_thread: threading.Thread | None = None
        self._phase_stop = threading.Event()

    def connect(self, connection_string: str):
        self.driver.connect(connection_string=connection_string)
        self.driver.set_notification_callback(self._nur_notification_callback)

        # STIX modules can come up still running a continuous inventory from
        # the previous session (especially after USB re-enumerate). RfidDemo
        # always sends STOPALLCONT right after PING; if we don't, our first
        # commands race with the module's stream and the radio appears
        # half-broken. Mirror that.
        try:
            self.driver.stop_all_cont()
        except Exception as e:
            logger.debug('stop_all_cont on connect: %s', e)

        self.get_details()

        # Set Senseid compatible mode.
        # SenseID tags only answer at BLF ~256 kHz Miller 4 (measured on the
        # STIX: nothing at 320 kHz M2 or 160 kHz M4).
        # AUTOPERIOD = NOT_IN_USE disables the STIX auto-stix periodic mode.
        # When AUTO is on, the module duty-cycles the carrier itself, which
        # halves (or worse) the observable read rate from the host. RfidDemo
        # disables it on every connect and the radio defaults aren't always
        # right after a power-cycle/re-plug.
        module_setup = ModuleSetup()
        module_setup.link_freq = ModuleSetupLinkFreq.BLF_256
        module_setup.rx_decoding = ModuleSetupRxDec.MILLER_4
        module_setup.inventory_q = 2
        module_setup.inventory_session = SESSION_PLAIN
        module_setup.inventory_target = ModuleSetupInvTarget.AB
        module_setup.period_setup = ModuleSetupPowerSave.NOT_IN_USE
        self.driver.set_module_setup(setup_flags=[ModuleSetupFlags.LINKFREQ,
                                                  ModuleSetupFlags.RXDEC,
                                                  ModuleSetupFlags.INVQ,
                                                  ModuleSetupFlags.INVSESSION,
                                                  ModuleSetupFlags.INVTARGET,
                                                  ModuleSetupFlags.AUTOPERIOD],
                                     module_setup=module_setup)
        self.driver.set_inventory_read_config(active=False)

        # Set MAX TX Power
        self.set_tx_power(self.details.max_tx_power)

        # Enable first antenna
        antenna_config = [False] * self.details.antenna_count
        antenna_config[0] = True
        self.set_antenna_config(antenna_config_array=antenna_config)
        return True

    def _build_tag(self, tag: NurTagDataMeta) -> SenseidTag:
        epc_bytes = bytearray(tag.epc) if tag.epc is not None else bytearray()
        epc_hex = bytes(epc_bytes).hex().upper()
        user_mem_hex = (bytes(tag.user_mem).hex().upper()
                        if tag.user_mem else None)

        farsens_pen = bytes(SENSEID_FARSENS_DEF.pen_header)
        if epc_bytes[:len(farsens_pen)] == farsens_pen:
            return SenseidFarsensTag(epc=epc_hex, user_mem_hex=user_mem_hex)

        if is_senseid_senseread_epc(epc_bytes):
            return SenseidSenseReadTag(epc=epc_hex, user_mem_hex=user_mem_hex)

        return SenseidRainTag(epc=epc_hex)

    def _nur_notification_callback(self, inventory_stream_notification: InventoryStreamNotification,
                                   tags: List[NurTagDataMeta]):
        with self._lock:
            # ACK first (the module asks for one on every notification), as
            # the NUR micro API does on reception, so it can go on reading
            # while the tags are handed over.
            self.driver.clear_notified_tags()
            # The module stops the stream on its own every ~20 s; restart it
            # unless the stop is ours (phase switch or stop_inventory_async).
            if inventory_stream_notification.stopped and self._running and not self._switching:
                logger.info('Restarting inventory stream')
                self.driver.start_inventory_stream()
            # In the plain phase of SENSEREAD, senseRead and Farsens tags come
            # without User memory (data=None, as a stale datagram would): they
            # still show up as alive, and tags that never answer the embedded
            # read are reported at all.
            if self.notification_callback is not None:
                for tag in tags:
                    self.notification_callback(self._build_tag(tag))

    def disconnect(self):
        self.stop_inventory_async()
        self.driver.disconnect()

    def get_details(self) -> SenseidReaderDetails:
        if self.details is None:
            reader_info = self.driver.get_reader_info()
            self.device_caps = self.driver.get_device_capabilities()

            module_setup = self.driver.get_module_setup(setup_flags=[ModuleSetupFlags.REGION])

            self.details = SenseidReaderDetails(
                model_name=reader_info.name,
                region=module_setup.region_id.name,
                firmware_version=reader_info.sw_version,
                antenna_count=reader_info.num_antennas,
                min_tx_power=self.device_caps.maxTxdBm - (self.device_caps.txSteps - 1) * self.device_caps.txAttnStep,
                max_tx_power=self.device_caps.maxTxdBm
            )
            logger.debug(self.details)
        return self.details

    def get_tx_power(self) -> float:
        # Only supporting same power on all antennas
        with self._lock:
            module_setup = self.driver.get_module_setup(setup_flags=[ModuleSetupFlags.TXLEVEL])
        current_tx_dbm = self.device_caps.maxTxdBm - module_setup.tx_level / self.device_caps.txAttnStep
        logger.debug('get_tx_power: ' + str(current_tx_dbm))
        return current_tx_dbm

    def set_tx_power(self, dbm: float):
        logger.debug('set_tx_power: ' + str(dbm))
        # Only supporting same power on all antennas
        if self.details is None:
            self.get_details()
        if dbm > self.details.max_tx_power:
            dbm = self.details.max_tx_power
            logger.warning('Power set to max power: ' + str(dbm))
        if dbm < self.details.min_tx_power:
            dbm = self.details.min_tx_power
            logger.warning('Power set to min power: ' + str(dbm))

        module_setup = ModuleSetup()
        module_setup.tx_level = int((self.device_caps.maxTxdBm - dbm) * self.device_caps.txAttnStep)
        with self._lock:
            self.driver.set_module_setup(setup_flags=[ModuleSetupFlags.TXLEVEL],
                                         module_setup=module_setup)

    def get_antenna_config(self) -> List[bool]:
        with self._lock:
            module_setup = self.driver.get_module_setup(setup_flags=[ModuleSetupFlags.ANTMASK])
        antenna_mask = module_setup.antenna_mask
        antenna_config_array = []
        for i in range(self.details.antenna_count):
            antenna_bit = (antenna_mask >> i) & 0b1
            antenna_config_array.append(bool(antenna_bit))
        logger.debug('get_antenna_config: ' + str(antenna_config_array))
        return antenna_config_array

    def set_antenna_config(self, antenna_config_array: List[bool]):
        logger.debug('set_antenna_config: ' + str(antenna_config_array))
        if not (True in antenna_config_array):
            antenna_config_array[0] = True
            logger.warning('At least one antenna needs to be active. Enabling antenna 1.')
        antenna_mask = 0
        for idx, antenna_config in enumerate(antenna_config_array):
            antenna_mask |= antenna_config << idx
        module_setup = ModuleSetup()
        module_setup.antenna_mask = antenna_mask
        module_setup.selected_antenna = 255  # Automatic selection
        with self._lock:
            self.driver.set_module_setup(setup_flags=[ModuleSetupFlags.ANTMASK,
                                                      ModuleSetupFlags.SELECTEDANT],
                                         module_setup=module_setup)

    def get_supported_modes(self) -> List[SenseidReaderMode]:
        return [SenseidReaderMode.SENSEID, SenseidReaderMode.SENSEREAD]

    def get_mode(self) -> SenseidReaderMode:
        return self._mode

    def set_mode(self, mode: SenseidReaderMode):
        super().set_mode(mode)
        running = self._running
        if running:
            self.stop_inventory_async()
        self._mode = mode
        logger.info('Reader mode set to %s', mode.value)
        if running:
            self.start_inventory_async(self.notification_callback, self.error_callback)

    def _configure_phase(self, ir: bool):
        """Session and embedded read for the next stream. Call with the stream stopped."""
        if ir:
            # Embedded user-mem read on every inventoried tag.
            # NUR firmware uses NUR_CMD_INVENTORYREAD (0x41) for this — the
            # similarly-named INVREADCONFIG (0x23) is rejected as
            # INVALID_COMMAND on this module class.
            # 6 words (the Farsens size) also covers every senseRead type.
            # On the STIX, 4 words made the senseRead RHAT return an all-zero
            # datagram in ~40% of the reads, while 3 and 6 words came back clean.
            word_count = max(SENSEID_SENSEREAD_DEF.word_count,
                             SENSEID_FARSENS_DEF.word_count)
            self.driver.set_inventory_read_config(
                active=True,
                bank=IrBank.USER,
                word_address=SENSEID_SENSEREAD_DEF.word_offset,
                word_length=word_count,
                ir_type=IrType.EPC_AND_DATA,
            )
        else:
            self.driver.set_inventory_read_config(active=False)
        setup = ModuleSetup()
        setup.inventory_session = SESSION_IR if ir else SESSION_PLAIN
        setup.inventory_target = ModuleSetupInvTarget.AB
        self.driver.set_module_setup(setup_flags=[ModuleSetupFlags.INVSESSION,
                                                  ModuleSetupFlags.INVTARGET],
                                     module_setup=setup)
        self._ir_active = ir

    def _senseread_phases(self):
        ir = True
        while not self._phase_stop.wait(SENSEREAD_IR_PHASE_S if ir else SENSEREAD_PLAIN_PHASE_S):
            ir = not ir
            with self._lock:
                if self._phase_stop.is_set():
                    break
                self._switching = True
                try:
                    self.driver.stop_inventory_stream()
                    self._configure_phase(ir)
                    self.driver.start_inventory_stream()
                except Exception as e:
                    logger.error('SENSEREAD phase switch failed: %s', e)
                finally:
                    self._switching = False

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None],
                              error_callback: Optional[Callable[['SenseidReaderError'], None]] = None):
        self.notification_callback = notification_callback
        self.error_callback = error_callback
        senseread = self._mode == SenseidReaderMode.SENSEREAD
        with self._lock:
            self._configure_phase(ir=senseread)
            self._running = True
            result = self.driver.start_inventory_stream()
        if senseread:
            logger.info('SENSEREAD: %.1f s with User-memory read (S%d) / %.1f s plain (S%d)',
                        SENSEREAD_IR_PHASE_S, SESSION_IR, SENSEREAD_PLAIN_PHASE_S, SESSION_PLAIN)
            self._phase_stop.clear()
            self._phase_thread = threading.Thread(target=self._senseread_phases, daemon=True,
                                                  name='SenseReadPhases')
            self._phase_thread.start()
        return result

    def stop_inventory_async(self):
        self._phase_stop.set()
        if self._phase_thread is not None:
            self._phase_thread.join(timeout=3)
            self._phase_thread = None
        with self._lock:
            was_running = self._running
            self._running = False
            if not was_running:
                return None
            result = self.driver.stop_inventory_stream()
            if self._ir_active:
                self.driver.set_inventory_read_config(active=False)
                self._ir_active = False
        return result
