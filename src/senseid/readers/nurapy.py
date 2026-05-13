import logging
from typing import List, Callable, Optional

from nurapy import NurAPY, NurTagDataMeta, InventoryStreamNotification, ModuleSetupFlags, ModuleSetup, NurDeviceCaps
from nurapy.protocol.command.inv_read_config import IrBank, IrType
from nurapy.protocol.command.module_setup import ModuleSetupLinkFreq, ModuleSetupRxDec, ModuleSetupInvTarget

from . import SenseidReader, SenseidReaderDetails, SenseidReaderError, SenseidReaderMode
from ..parsers import SenseidTag
from ..parsers.farsens import SenseidFarsensTag
from ..parsers.farsens.yaml import SENSEID_FARSENS_DEF
from ..parsers.legacy import SenseidLegacyTag
from ..parsers.legacy.yaml import SENSEID_LEGACY_DEF
from ..parsers.rain import SenseidRainTag

logger = logging.getLogger(__name__)


class SenseidNurapy(SenseidReader):

    def __init__(self):
        self.driver = NurAPY()
        self.notification_callback = None
        self.error_callback = None
        self.device_caps: NurDeviceCaps | None = None
        self.details = None
        self._mode: SenseidReaderMode = SenseidReaderMode.SENSEID

    def connect(self, connection_string: str):
        self.driver.connect(connection_string=connection_string)
        self.driver.set_notification_callback(self._nur_notification_callback)
        self.get_details()

        # Set Senseid compatible mode
        module_setup = ModuleSetup()
        module_setup.link_freq = ModuleSetupLinkFreq.BLF_256
        module_setup.rx_decoding = ModuleSetupRxDec.MILLER_4
        module_setup.inventory_q = 2
        module_setup.inventory_session = 0
        module_setup.inventory_target = ModuleSetupInvTarget.AB
        self.driver.set_module_setup(setup_flags=[ModuleSetupFlags.LINKFREQ,
                                                  ModuleSetupFlags.RXDEC,
                                                  ModuleSetupFlags.INVQ,
                                                  ModuleSetupFlags.INVSESSION,
                                                  ModuleSetupFlags.INVTARGET],
                                     module_setup=module_setup)

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

        legacy_pen = bytes(SENSEID_LEGACY_DEF.pen_header)
        marker_offset = len(legacy_pen) + 1
        if (len(epc_bytes) > marker_offset
                and epc_bytes[:len(legacy_pen)] == legacy_pen
                and epc_bytes[marker_offset] == SENSEID_LEGACY_DEF.epc_family_marker):
            return SenseidLegacyTag(epc=epc_hex, user_mem_hex=user_mem_hex)

        return SenseidRainTag(epc=epc_hex)

    def _nur_notification_callback(self, inventory_stream_notification: InventoryStreamNotification,
                                   tags: List[NurTagDataMeta]):
        if inventory_stream_notification.stopped:
            logger.info('Restarting inventory stream')
            self.driver.start_inventory_stream()
        if self.notification_callback is not None:
            for tag in tags:
                self.notification_callback(self._build_tag(tag))
        self.driver.clear_notified_tags()

    def disconnect(self):
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
        self.driver.set_module_setup(setup_flags=[ModuleSetupFlags.TXLEVEL],
                                     module_setup=module_setup)

    def get_antenna_config(self) -> List[bool]:
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
        self.driver.set_module_setup(setup_flags=[ModuleSetupFlags.ANTMASK,
                                                  ModuleSetupFlags.SELECTEDANT],
                                     module_setup=module_setup)

    def get_supported_modes(self) -> List[SenseidReaderMode]:
        return [SenseidReaderMode.SENSEID, SenseidReaderMode.LEGACY]

    def get_mode(self) -> SenseidReaderMode:
        return self._mode

    def set_mode(self, mode: SenseidReaderMode):
        super().set_mode(mode)
        self._mode = mode
        if mode == SenseidReaderMode.LEGACY:
            # Embedded user-mem read on every inventoried tag.
            # NUR firmware uses NUR_CMD_INVENTORYREAD (0x41) for this — the
            # similarly-named INVREADCONFIG (0x23) is rejected as
            # INVALID_COMMAND on this module class.
            word_count = max(SENSEID_LEGACY_DEF.word_count,
                             SENSEID_FARSENS_DEF.word_count)
            self.driver.set_inventory_read_config(
                active=True,
                bank=IrBank.USER,
                word_address=SENSEID_LEGACY_DEF.word_offset,
                word_length=word_count,
                ir_type=IrType.EPC_AND_DATA,
            )
            # Session 1 + dual target: tag flag persists ~0.5-5s after read
            # so we get re-reads at a sensible cadence (not every round) and
            # the AB sweep keeps both A and B tags responding.
            setup = ModuleSetup()
            setup.inventory_session = 1
            setup.inventory_target = ModuleSetupInvTarget.AB
            self.driver.set_module_setup(setup_flags=[ModuleSetupFlags.INVSESSION,
                                                      ModuleSetupFlags.INVTARGET],
                                         module_setup=setup)
            logger.info('Reader mode set to LEGACY (USER@0x%X, %d words, session=1, target=AB)',
                        SENSEID_LEGACY_DEF.word_offset, word_count)
        else:
            self.driver.set_inventory_read_config(active=False)
            logger.info('Reader mode set to %s (no embedded memory reads)',
                        mode.value)

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None],
                              error_callback: Optional[Callable[['SenseidReaderError'], None]] = None):
        self.notification_callback = notification_callback
        self.error_callback = error_callback
        return self.driver.start_inventory_stream()

    def stop_inventory_async(self):
        return self.driver.stop_inventory_stream()
