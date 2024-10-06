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
        self.driver.ConnectSerialPortEx(port_name=connection_string)
        self.driver.set_notification_callback(self._nur_notification_callback)
        self.get_details()

        # Set Senseid compatible mode
        module_setup = NurModuleSetup()
        module_setup.link_freq = SETUP_LINK_FREQ.BLF_256
        module_setup.rx_decoding = SETUP_RX_DEC.MILLER_4
        self.driver.SetModuleSetup(setup_flags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_LINKFREQ,
                                               NUR_MODULESETUP_FLAGS.NUR_SETUP_RXDEC], module_setup=module_setup)

        # Set MAX TX Power
        self.set_tx_power(self.details.max_tx_power)

        # Enable first antenna
        antenna_config = [False] * self.details.antenna_count
        antenna_config[0] = True
        self.set_antenna_config(antenna_config_array=antenna_config)
        return True

    def _nur_notification_callback(self, inventory_stream_data):
        # If stream stopped, restart
        if inventory_stream_data.stopped:
            self.driver.StartInventoryStream(rounds=10, q=0, session=0)

        # Check number of tags read
        tag_count = self.driver.GetTagCount()
        # Get data of read tags
        for idx in range(tag_count):
            tag_data = self.driver.GetTagData(idx=idx)
            if self.notification_callback is not None:
                self.notification_callback(SenseidRainTag(epc=tag_data.epc))
        self.driver.ClearTags()

    def disconnect(self):
        self.driver.Disconnect()

    def get_details(self) -> SenseidReaderDetails:
        if self.details is None:
            reader_info = self.driver.GetReaderInfo()
            self.device_caps = self.driver.GetDeviceCaps()

            module_setup = self.driver.GetModuleSetup(setup_flags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_REGION])

            self.details = SenseidReaderDetails(
                model_name=reader_info.name,
                region=module_setup.region_id.name,
                firmware_version=str(reader_info.sw_ver_major) + '.' + str(reader_info.sw_ver_minor),
                antenna_count=reader_info.num_antennas,
                min_tx_power=self.device_caps.maxTxdBm - (self.device_caps.txSteps-1) * self.device_caps.txAttnStep,
                max_tx_power=self.device_caps.maxTxdBm
            )
            logger.debug(self.details)
        return self.details

    def get_tx_power(self) -> float:
        # Only supporting same power on all antennas
        module_setup = self.driver.GetModuleSetup(setup_flags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_TXLEVEL])
        current_tx_dbm = self.device_caps.maxTxdBm - module_setup.tx_level / self.device_caps.txAttnStep
        logger.debug('get_tx_power: ' + str(current_tx_dbm))
        return current_tx_dbm

    def set_tx_power(self, dbm: float):
        logger.debug('set_tx_power: ' + str(dbm))
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
        module_setup.tx_level = (self.device_caps.maxTxdBm - dbm) * self.device_caps.txAttnStep
        self.driver.SetModuleSetup(setup_flags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_TXLEVEL], module_setup=module_setup)

    def get_antenna_config(self) -> List[bool]:
        module_setup = self.driver.GetModuleSetup(setup_flags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_ANTMASKEX])
        antenna_mask = module_setup.antenna_mask_ex
        antenna_config_array = []
        for i in range(self.details.antenna_count):
            antenna_bit = (antenna_mask >> i) & 0b1
            antenna_config_array.append(bool(antenna_bit))
        logger.debug('get_antenna_config: ' + str(antenna_config_array))
        return antenna_config_array

    def set_antenna_config(self, antenna_config_array: List[bool]):
        logger.debug('set_antenna_config: ' + str(antenna_config_array))
        if not (True in antenna_config_array):
            antenna_config_array[0] = True
            logger.warning('At least one antenna needs to be active. Enabling antenna 1.')
        antenna_mask = 0
        for idx, antenna_config in enumerate(antenna_config_array):
            antenna_mask |= antenna_config << idx
        module_setup = NurModuleSetup()
        module_setup.antenna_mask_ex = antenna_mask
        module_setup.selected_antenna = -1  # Automatic selection
        self.driver.SetModuleSetup(setup_flags=[NUR_MODULESETUP_FLAGS.NUR_SETUP_ANTMASKEX,
                                               NUR_MODULESETUP_FLAGS.NUR_SETUP_SELECTEDANT],
                                   module_setup=module_setup)

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None]):
        self.notification_callback = notification_callback
        return self.driver.StartInventoryStream(rounds=10, q=0, session=0)

    def stop_inventory_async(self):
        return self.driver.StopInventoryStream()
