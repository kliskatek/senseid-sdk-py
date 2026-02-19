import logging
from typing import List, Callable

from driver_sble_py_klsblelcf import KlSbleLcr

from . import SenseidReader, SenseidReaderDetails
from ..parsers import SenseidTag
from ..parsers.ble import SenseidBleTag

logger = logging.getLogger(__name__)


class SenseidKlSbleLcr(SenseidReader):

    def __init__(self):
        self.details = None
        self.driver = KlSbleLcr()
        self.notification_callback = None
        self.tx_power = 0

    def connect(self, connection_string: str):
        self.driver.connect(connection_string=connection_string)
        self.driver.set_notification_callback(self._sble_notification_callback)
        return True

    def _sble_notification_callback(self, beacon):
        if self.notification_callback is not None:
            self.notification_callback(SenseidBleTag(beacon))
        pass

    def disconnect(self):
        self.driver.disconnect()

    def get_details(self) -> SenseidReaderDetails:
        if self.details is None:
            self.details = SenseidReaderDetails(
                model_name='KL-SBLE-LCR',
                region='EU',
                firmware_version='1.0.0',
                antenna_count=1,
                min_tx_power=10,
                max_tx_power=31.5
            )
            logger.debug(self.details)
        return self.details

    def get_tx_power(self) -> float:
        return self.driver.get_tx_power()

    def set_tx_power(self, dbm: float):
        return self.driver.set_tx_power(dbm)

    def get_antenna_config(self) -> List[bool]:
        antenna_config_array = [True]
        return antenna_config_array

    def set_antenna_config(self, antenna_config_array: List[bool]):
        logger.debug('Antenna configuration is fixed')

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None]):
        self.notification_callback = notification_callback
        return self.driver.start()

    def stop_inventory_async(self):
        return self.driver.stop()
