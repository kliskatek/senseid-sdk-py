import logging
from typing import List, Callable

from redrcp import RedRcp, NotificationTpeCuiii, NotificationTpeCuiiiRssi, NotificationTpeCuiiiTid, AntiCollisionMode, \
    ParamDR, ParamModulation, ParamSel, ParamSession, ParamTarget

from ..parsers import SenseidTag
from ..parsers.rain import SenseidRainTag
from ..readers import SenseidReader, SenseidReaderDetails


class SenseidReaderRedRcp(SenseidReader):

    def __init__(self):
        self.driver = RedRcp()
        self.notification_callback = None
        self.details = None

    def connect(self, connection_string: str):
        if not self.driver.connect(connection_string=connection_string):
            return False
        self.driver.set_notification_callback(self._redrcp_notification_callback)
        self.driver.set_anti_collision_mode(AntiCollisionMode.MANUAL, start_q=4, min_q=0, max_q=7)
        self.driver.set_query_parameters(dr=ParamDR.DR_64_DIV_3,
                                         modulation=ParamModulation.MILLER_4,
                                         pilot_tone=False,
                                         sel=ParamSel.ALL_0,
                                         session=ParamSession.S1,
                                         target=ParamTarget.A,
                                         target_toggle=True,
                                         q=4)
        return True

    def _redrcp_notification_callback(self, red_rcp_notification: NotificationTpeCuiii |
                                                                  NotificationTpeCuiiiRssi |
                                                                  NotificationTpeCuiiiTid):
        if self.notification_callback is not None:
            self.notification_callback(SenseidRainTag(epc=red_rcp_notification.epc))

    def disconnect(self):
        self.driver.disconnect()

    def get_details(self):
        info_model = self.driver.get_info_model()
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

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None]):
        self.notification_callback = notification_callback
        return self.driver.start_auto_read2()

    def stop_inventory_async(self):
        if self.driver.is_connected():
            return self.driver.stop_auto_read2()
