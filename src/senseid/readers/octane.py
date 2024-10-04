import logging
from typing import List

from src.py_octane import Octane, OctaneReaderMode, OctaneSearchMode
from src.py_senseid.readers import SenseidReader, SenseidReaderDetails


class SenseidOctane(SenseidReader):

    def __init__(self, connection_string, notification_callback):
        self.connection_string = connection_string
        self.notification_callback = notification_callback
        self.driver = Octane()
        self.details: SenseidReaderDetails | None = None

    def connect(self):
        if not self.driver.connect(ip=self.connection_string):
            return False
        self.driver.set_notification_callback(self.notification_callback)
        self.get_details()
        self.driver.set_mode(reader_mode=OctaneReaderMode.DenseReaderM4, search_mode=OctaneSearchMode.DualTarget, session=1)
        self.driver.set_tx_power(self.details.max_tx_power)
        antenna_config = [False]*self.details.antenna_count
        antenna_config[0] = True
        self.driver.set_antenna_config(antenna_config)
        return True

    def disconnect(self):
        self.driver.disconnect()

    def get_details(self):
        reader_capabilities = self.driver.query_feature_set()
        self.details = SenseidReaderDetails(
            model_name=reader_capabilities.ModelName,
            region=reader_capabilities.CommunicationsStandard.ToString(),
            firmware_version=reader_capabilities.FirmwareVersion,
            antenna_count=reader_capabilities.AntennaCount,
            min_tx_power=reader_capabilities.TxPowers[0].Dbm,
            max_tx_power=reader_capabilities.TxPowers[len(reader_capabilities.TxPowers) - 1].Dbm
        )
        return self.details

    def get_tx_power(self):
        # Only supporting same power on all antennas
        return self.driver.get_tx_power()

    def set_tx_power(self, dbm):
        # Only supporting same power on all antennas
        if self.details is None:
            self.get_details()
        if dbm > self.details.max_tx_power:
            dbm = self.details.max_tx_power
            logging.warning('Power set to max power: ' + str(dbm))
        if dbm < self.details.min_tx_power:
            dbm = self.details.min_tx_power
            logging.warning('Power set to min power: ' + str(dbm))
        self.driver.set_tx_power(dbm=dbm)

    def get_antenna_config(self):
        antenna_config_array = self.driver.get_antenna_config()
        return antenna_config_array

    def set_antenna_config(self, antenna_config_array: List[bool]):
        if not True in antenna_config_array:
            antenna_config_array[0] = True
            logging.warning('At least one antenna needs to be active. Enabling antenna 1.')
        self.driver.set_antenna_config(antenna_config_array)

    def start_inventory_async(self):
        return self.driver.start_inventory()

    def stop_inventory_async(self):
        return self.driver.stop_inventory()
