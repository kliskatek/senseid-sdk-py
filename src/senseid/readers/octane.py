import logging
from typing import List, Callable

from octane_sdk_wrapper import Octane, OctaneReaderMode, OctaneSearchMode, OctaneTagReport

from . import SenseidReader, SenseidReaderDetails
from ..parsers import SenseidTag
from ..parsers.rain import SenseidRainTag

logger = logging.getLogger(__name__)


class SenseidOctane(SenseidReader):

    def __init__(self):
        self.driver = Octane()
        self.notification_callback = None
        self.details = None

    def connect(self, connection_string: str):
        if not self.driver.connect(ip=connection_string):
            return False
        self.driver.set_notification_callback(self._octane_notification_callback)
        self.get_details()
        # Set Senseid compatible mode
        self.driver.set_mode(reader_mode=OctaneReaderMode.DenseReaderM4, search_mode=OctaneSearchMode.DualTarget,
                             session=1)
        # Set MAX TX Power
        self.driver.set_tx_power(self.details.max_tx_power)
        # Enable first antenna
        antenna_config = [False] * self.details.antenna_count
        antenna_config[0] = True
        self.driver.set_antenna_config(antenna_config)
        return True

    def _octane_notification_callback(self, octane_tag_report: OctaneTagReport):
        if self.notification_callback is not None:
            self.notification_callback(SenseidRainTag(epc=octane_tag_report.Epc))

    def disconnect(self):
        self.driver.disconnect()

    def get_details(self) -> SenseidReaderDetails:
        if self.details is None:
            feature_set = self.driver.query_feature_set()
            self.details = SenseidReaderDetails(
                model_name=feature_set.model_name,
                region=feature_set.region,
                firmware_version=feature_set.firmware_version,
                antenna_count=feature_set.antenna_count,
                min_tx_power=feature_set.min_tx_power,
                max_tx_power=feature_set.max_tx_power
            )
        return self.details

    def get_tx_power(self) -> float:
        # Only supporting same power on all antennas
        return self.driver.get_tx_power()

    def set_tx_power(self, dbm: float):
        # Only supporting same power on all antennas
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
        antenna_config_array = self.driver.get_antenna_config()
        return antenna_config_array

    def set_antenna_config(self, antenna_config_array: List[bool]):
        if not (True in antenna_config_array):
            antenna_config_array[0] = True
            logger.warning('At least one antenna needs to be active. Enabling antenna 1.')
        self.driver.set_antenna_config(antenna_config_array)

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None]):
        self.notification_callback = notification_callback
        return self.driver.start()

    def stop_inventory_async(self):
        return self.driver.stop()
