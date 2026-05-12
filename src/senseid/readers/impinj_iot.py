import logging
from typing import List, Callable, Optional

from impinj_iot import ImpinjIot, ImpinjIotTagReport, RfMode

from . import SenseidReader, SenseidReaderDetails, SenseidReaderError, SenseidReaderMode
from ..parsers import SenseidTag
from ..parsers.legacy import SenseidLegacyTag
from ..parsers.legacy.yaml import SENSEID_LEGACY_DEF
from ..parsers.rain import SenseidRainTag

logger = logging.getLogger(__name__)


class SenseidImpinjIot(SenseidReader):

    def __init__(self):
        self.driver = ImpinjIot()
        self.notification_callback = None
        self.error_callback = None
        self.details = None
        self._mode: SenseidReaderMode = SenseidReaderMode.SENSEID

    def connect(self, connection_string: str):
        if not self.driver.connect(ip=connection_string):
            return False
        self.driver.set_notification_callback(self._driver_notification_callback)
        self.get_details()
        # Set MAX TX Power
        self.driver.set_tx_power(self.details.max_tx_power)
        # Enable first antenna
        antenna_config = [False] * self.details.antenna_count
        antenna_config[0] = True
        self.driver.set_antenna_config(antenna_config)
        # Set SenseID compatible RF mode (static 246 = M4, BLF 320kHz, Tari 15.6us,
        # DR 64/3). LLRP DENSE_READER_M4 would map similar in ETSI but tag-side
        # behaviour can differ slightly; pin the static mode for determinism.
        self.driver.set_rf_mode(RfMode.STATIC_246)
        return True

    def _driver_notification_callback(self, tag_report: ImpinjIotTagReport):
        if self.notification_callback is None:
            return
        if self._mode == SenseidReaderMode.LEGACY:
            tag = SenseidLegacyTag(epc=tag_report.epc, user_mem_hex=tag_report.user_mem)
        else:
            tag = SenseidRainTag(epc=tag_report.epc)
        self.notification_callback(tag)

    def disconnect(self):
        self.driver.disconnect()

    def get_details(self) -> SenseidReaderDetails:
        if self.details is None:
            info = self.driver.get_reader_info()
            if info is None:
                return None
            self.details = SenseidReaderDetails(
                model_name=info.model,
                region=info.region,
                firmware_version=info.firmware_version,
                antenna_count=info.antenna_count,
                min_tx_power=info.min_tx_power_cdbm / 100.0,
                max_tx_power=info.max_tx_power_cdbm / 100.0,
                technology=self.technology,
            )
        return self.details

    def get_tx_power(self) -> float:
        return self.driver.get_tx_power()

    def set_tx_power(self, dbm: float):
        if self.details is None:
            self.get_details()
        if dbm > self.details.max_tx_power:
            dbm = self.details.max_tx_power
            logger.warning('Power set to max power: ' + str(dbm))
        if dbm < self.details.min_tx_power:
            dbm = self.details.min_tx_power
            logger.warning('Power set to min power: ' + str(dbm))
        self.driver.set_tx_power(dbm=dbm)

    def get_antenna_config(self) -> List[bool]:
        return self.driver.get_antenna_config()

    def set_antenna_config(self, antenna_config_array: List[bool]):
        if not (True in antenna_config_array):
            antenna_config_array[0] = True
            logger.warning('At least one antenna needs to be active. Enabling antenna 1.')
        self.driver.set_antenna_config(antenna_config_array)

    def get_supported_modes(self) -> List[SenseidReaderMode]:
        return [SenseidReaderMode.SENSEID, SenseidReaderMode.LEGACY]

    def get_mode(self) -> SenseidReaderMode:
        return self._mode

    def set_mode(self, mode: SenseidReaderMode):
        super().set_mode(mode)
        self._mode = mode
        if mode == SenseidReaderMode.LEGACY:
            reads = [{
                'memoryBank': SENSEID_LEGACY_DEF.memory_bank.value,
                'wordOffset': SENSEID_LEGACY_DEF.word_offset,
                'wordCount': SENSEID_LEGACY_DEF.word_count,
            }]
            self.driver.set_tag_memory_reads(reads)
            logger.info('Reader mode set to LEGACY (tagMemoryReads=%s)', reads)
        else:
            self.driver.set_tag_memory_reads(None)
            logger.info('Reader mode set to %s (no embedded memory reads)', mode.value)

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None],
                              error_callback: Optional[Callable[['SenseidReaderError'], None]] = None):
        self.notification_callback = notification_callback
        self.error_callback = error_callback
        return self.driver.start()

    def stop_inventory_async(self):
        return self.driver.stop()
