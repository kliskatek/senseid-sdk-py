import logging
import time
from typing import List, Callable, Optional

from zebra_llrp import ZebraLlrp, ZebraLlrpTagReport, FX9600RfMode

from . import SenseidReader, SenseidReaderDetails, SenseidReaderError
from ..parsers import SenseidTag
from ..parsers.rain import SenseidRainTag

logger = logging.getLogger(__name__)


class SenseidZebraLlrp(SenseidReader):

    def __init__(self):
        self.driver = ZebraLlrp()
        self.notification_callback = None
        self.error_callback = None
        self.details = None

    def connect(self, connection_string: str):
        if not self.driver.connect(ip=connection_string):
            return False
        self.driver.set_notification_callback(self._driver_notification_callback)
        # Wait for capabilities (FX9600 can take ~3s)
        for _ in range(40):
            info = self.driver.get_reader_info()
            if info and info.firmware_version:
                break
            time.sleep(0.1)
        self.get_details()
        # Set MAX TX Power (index 0 = max power)
        self.driver.set_tx_power(0)
        # Enable first antenna
        self.driver.set_antenna_config([1])
        # Set SenseID compatible RF mode (M4, dense reader)
        self.driver.set_rf_mode(FX9600RfMode.M4_BLF256_T25_P15)
        return True

    def _driver_notification_callback(self, tag_report: ZebraLlrpTagReport):
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
        if self.details is None:
            self.get_details()
        if dbm >= self.details.max_tx_power:
            dbm = self.details.max_tx_power
            # Use index 0 = max power (avoids index out of range)
            self.driver.set_tx_power(0)
            return
        if dbm < self.details.min_tx_power:
            dbm = self.details.min_tx_power
            logger.warning('Power set to min power: ' + str(dbm))
        self.driver.set_tx_power_dbm(dbm=dbm)

    def get_antenna_config(self) -> List[bool]:
        active_ports = self.driver.get_antenna_config()
        if self.details is None:
            self.get_details()
        config = [False] * (self.details.antenna_count if self.details else 4)
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
