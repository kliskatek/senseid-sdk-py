import logging
from typing import List

from src.py_redrcp import RedRcp
from src.py_senseid.readers import SenseidReader, SenseidReaderDetails


class SenseidReaderRedRcp(SenseidReader):

    def __init__(self, connection_string, notification_callback):
        self.connection_string = connection_string
        self.notification_callback = notification_callback
        self.driver = RedRcp()
        self.details = None

    def connect(self):
        if not self.driver.connect(port=self.connection_string):
            return False
        self.driver.set_notification_callback(self.notification_callback)
        return True

    def disconnect(self):
        self.driver.disconnect()

    def get_details(self):
        info_model = self.driver.get_info_model()
        info_manufacturer = self.driver.get_info_manufacturer()
        info_fw_version = self.driver.get_info_fw_version()
        info_detail = self.driver.get_info_detail()
        self.details = SenseidReaderDetails(
            model_name=info_model,
            region=info_detail.region.name,
            firmware_version=info_fw_version,
            antenna_count=1,
            min_tx_power=info_detail.min_tx_power,
            max_tx_power=info_detail.max_tx_power
        )
        return self.details

    def get_tx_power(self):
        return self.driver.get_tx_power()

    def set_tx_power(self, dbm):
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
        # RED4S has a single antenna
        antenna_config_array: List[bool] = [True]
        return antenna_config_array

    def set_antenna_config(self, antenna_config_array: List[bool]):
        # RED4S has a single antenna
        pass

    def start_inventory_async(self):
        return self.driver.start_auto_read2()

    def stop_inventory_async(self):
        if self.driver.is_connected():
            return self.driver.stop_auto_read2()
