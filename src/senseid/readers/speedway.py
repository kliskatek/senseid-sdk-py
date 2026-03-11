import logging
from typing import List, Callable, Optional

from impinj_llrp import ImpinjLlrp, ImpinjLlrpTagReport, ImpinjReaderMode, ImpinjSearchMode

from . import SenseidReader, SenseidReaderDetails, SenseidReaderError
from ..parsers import SenseidTag
from ..parsers.rain import SenseidRainTag

logger = logging.getLogger(__name__)


class SenseidSpeedway(SenseidReader):

    def __init__(self):
        self.driver = ImpinjLlrp()
        self.notification_callback = None
        self.error_callback = None
        self.details = None

    def connect(self, connection_string: str):
        if not self.driver.connect(ip=connection_string):
            return False
        self.driver.set_notification_callback(self._driver_notification_callback)
        self.get_details()
        return True

    def _driver_notification_callback(self, tag_report: ImpinjLlrpTagReport):
        if self.notification_callback is not None:
            self.notification_callback(SenseidRainTag(epc=tag_report.epc))

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
                min_tx_power=info.min_tx_power_dbm,
                max_tx_power=info.max_tx_power_dbm,
            )
        return self.details

    def get_tx_power(self) -> float:
        return self.driver.get_tx_power_dbm()

    def set_tx_power(self, dbm: float):
        self.driver.set_tx_power_dbm(dbm)

    def get_antenna_config(self) -> List[bool]:
        active_ports = self.driver.get_antenna_config()
        if self.details is None:
            self.get_details()
        count = self.details.antenna_count if self.details else 4
        config = [False] * count
        for port in active_ports:
            if 1 <= port <= len(config):
                config[port - 1] = True
        return config

    def set_antenna_config(self, antenna_config_array: List[bool]):
        if not (True in antenna_config_array):
            antenna_config_array[0] = True
            logger.warning('At least one antenna needs to be active. Enabling antenna 1.')
        active_ports = [idx + 1 for idx, enabled in enumerate(antenna_config_array) if enabled]
        self.driver.set_antenna_config(active_ports)

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None],
                              error_callback: Optional[Callable[['SenseidReaderError'], None]] = None):
        self.notification_callback = notification_callback
        self.error_callback = error_callback
        return self.driver.start()

    def stop_inventory_async(self):
        return self.driver.stop()
