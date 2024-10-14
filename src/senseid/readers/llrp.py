import logging
import time
from typing import List, Callable

from octane_sdk_wrapper import Octane, OctaneReaderMode, OctaneSearchMode, OctaneTagReport
from sllurp.llrp import LLRPReaderClient, LLRPReaderConfig, LLRP_DEFAULT_PORT, LLRPReaderState

from . import SenseidReader, SenseidReaderDetails
from ..parsers import SenseidTag
from ..parsers.rain import SenseidRainTag

logger = logging.getLogger(__name__)


class SenseidLlrp(SenseidReader):

    def __init__(self):
        self.driver: LLRPReaderClient | None = None
        self.config: LLRPReaderConfig | None = None
        self.notification_callback = None
        self.details = None
        self._tx_power: float | None = None
        self._antennas: List[bool] | None = None

    def connect(self, connection_string: str):
        try:
            self.config = LLRPReaderConfig()
            self.config.start_inventory = False
            self.driver = LLRPReaderClient('192.168.17.246', LLRP_DEFAULT_PORT, self.config)

            capabilities_received = False

            def on_get_capabilities(reader: LLRPReaderClient, state):
                nonlocal capabilities_received
                if state == LLRPReaderState.STATE_SENT_GET_CONFIG:
                    if not capabilities_received:
                        logger.debug('TODO: parse capabilities')
                        logger.debug(reader.llrp.capabilities)
                        capabilities_received = True

            self.driver.add_state_callback(LLRPReaderState.STATE_SENT_GET_CONFIG, on_get_capabilities)
            self.driver.add_tag_report_callback(self._llrp_notification_callback)
            self.driver.connect()

            while not capabilities_received:
                time.sleep(0.1)

            return True
        except Exception as e:
            logger.error(e)
            return False

    def _llrp_notification_callback(self, reader: LLRPReaderClient, tag_reports):
        logger.debug(tag_reports)
        #if self.notification_callback is not None:
        #    self.notification_callback(SenseidRainTag(epc=octane_tag_report.Epc))

    def disconnect(self):
        self.driver.disconnect()
        self.driver.join()

    def get_details(self) -> SenseidReaderDetails:
        return self.details

    def get_tx_power(self) -> float:
        # Only supporting same power on all antennas
        return self._tx_power

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
        #self.driver.set_tx_power(dbm=dbm)

    def get_antenna_config(self) -> List[bool]:
        return self._antennas

    def set_antenna_config(self, antenna_config_array: List[bool]):
        if not (True in antenna_config_array):
            antenna_config_array[0] = True
            logger.warning('At least one antenna needs to be active. Enabling antenna 1.')
        #self.driver.set_antenna_config(antenna_config_array)

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None]):
        self.notification_callback = notification_callback
        self.config.start_inventory = True
        self.config.duration = 0.2
        self.driver.update_config(self.config)

    def stop_inventory_async(self):
        self.config.start_inventory = False
        self.driver.update_config(self.config)
