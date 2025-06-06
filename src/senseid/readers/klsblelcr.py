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
                firmware_version='0.0.1',
                antenna_count=1,
                min_tx_power=10,
                max_tx_power=31.5
            )
            logger.debug(self.details)
        return self.details

    def get_tx_power(self) -> float:
        current_tx_dbm = 10
        logger.debug('get_tx_power: ' + str(current_tx_dbm))
        return current_tx_dbm

    def set_tx_power(self, dbm: float):
        logger.debug('set_tx_power: ' + str(dbm))

    def get_antenna_config(self) -> List[bool]:
        antenna_config_array = [True]
        return antenna_config_array

    def set_antenna_config(self, antenna_config_array: List[bool]):
        logger.debug('set_antenna_config: ' + str(antenna_config_array))

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None]):
        self.notification_callback = notification_callback
        return self.driver.configure_cw(True, 500, 500)

    def stop_inventory_async(self):
        return self.driver.configure_cw(False, 0, 0)
