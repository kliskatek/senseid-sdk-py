import logging
from typing import List, Callable

from nurapi import NUR, NUR_MODULESETUP_FLAGS, NurModuleSetup, NurReaderInfo, NurDeviceCaps, NurTagCount, NurTagData
from nurapi.enums import SETUP_LINK_FREQ, SETUP_RX_DEC, OperationResult

from . import SenseidReader, SenseidReaderDetails
from ..parsers import SenseidTag
from ..parsers.rain import SenseidRainTag

logger = logging.getLogger(__name__)


class SenseidNurapi(SenseidReader):

    def __init__(self):
        self.driver = NUR()
        self.notification_callback = None
        self.device_caps: NurDeviceCaps | None = None
        self.details = None

    def connect(self, connection_string: str):
        if self.driver.ConnectSerialPortEx(port_name=connection_string) != OperationResult.SUCCESS:
            return False
        self.driver.set_user_inventory_notification_callback(self._nur_notification_callback)
        self.get_details()

        module_setup = NurModuleSetup()
        # Let API initialize setup with current values
        self.driver.GetModuleSetup(setupFlags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_LINKFREQ,
                                               NUR_MODULESETUP_FLAGS.NUR_SETUP_RXDEC], module_setup=module_setup)

        # Set desired configuration
        module_setup.link_freq = SETUP_LINK_FREQ.BLF_256
        module_setup.rx_decoding = SETUP_RX_DEC.MILLER_4
        self.driver.SetModuleSetup(setupFlags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_LINKFREQ,
                                               NUR_MODULESETUP_FLAGS.NUR_SETUP_RXDEC], module_setup=module_setup)

        # set tx power max
        antenna_config = [False] * self.details.antenna_count
        antenna_config[0] = True
        # set antenna config
        return True

    def _nur_notification_callback(self, inventory_stream_data):
        # If stream stopped, restart
        if inventory_stream_data.stopped:
            self.driver.StartInventoryStream(rounds=10, q=0, session=0)

        # Check number of tags read
        tag_count = NurTagCount()
        self.driver.GetTagCount(tag_count=tag_count)
        # Get data of read tags
        for idx in range(tag_count.count):
            tag_data = NurTagData()
            self.driver.GetTagData(idx=idx, tag_data=tag_data)
            if self.notification_callback is not None:
                self.notification_callback(SenseidRainTag(epc=tag_data.epc))
        self.driver.ClearTags()

    def disconnect(self):
        self.driver.Disconnect()

    def get_details(self) -> SenseidReaderDetails:
        if self.details is None:
            reader_info = NurReaderInfo()
            self.driver.GetReaderInfo(reader_info=reader_info)
            self.device_caps = NurDeviceCaps()
            self.driver.GetDeviceCaps(device_caps=self.device_caps)

            module_setup = NurModuleSetup()
            # Let API initialize setup with current values
            self.driver.GetModuleSetup(setupFlags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_REGION], module_setup=module_setup)

            self.details = SenseidReaderDetails(
                model_name=reader_info.name,
                region=module_setup.region_id.name,
                firmware_version=str(reader_info.sw_ver_major) + '.' + str(reader_info.sw_ver_minor),
                antenna_count=reader_info.num_antennas,
                min_tx_power=self.device_caps.maxTxdBm - self.device_caps.txSteps * self.device_caps.txAttnStep,
                max_tx_power=self.device_caps.maxTxdBm
            )
            logger.debug(self.details)
        return self.details

    def get_tx_power(self) -> float:
        # Only supporting same power on all antennas
        module_setup = NurModuleSetup()
        self.driver.GetModuleSetup(setupFlags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_TXLEVEL], module_setup=module_setup)
        current_tx_dbm = self.device_caps.maxTxdBm - module_setup.tx_level/self.device_caps.txAttnStep
        return current_tx_dbm

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

        module_setup = NurModuleSetup()
        self.driver.GetModuleSetup(setupFlags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_TXLEVEL], module_setup=module_setup)

        module_setup.tx_level = (self.device_caps.maxTxdBm - dbm) * self.device_caps.txAttnStep
        self.driver.SetModuleSetup(setupFlags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_TXLEVEL], module_setup=module_setup)


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
        return self.driver.StartInventoryStream(rounds=10, q=0, session=0)

    def stop_inventory_async(self):
        return self.driver.StopInventoryStream()
