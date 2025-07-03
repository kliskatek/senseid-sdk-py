import logging
import platform
import time
from threading import Thread
from typing import Callable

import serial
import serial.tools.list_ports
from usbmonitor import USBMonitor

from .. import SenseidReaderConnectionInfo, SupportedSenseidReader

logger = logging.getLogger(__name__)


class SerialPortScanner:

    def __init__(self, notification_callback: Callable[[SenseidReaderConnectionInfo], None]):
        self.notification_callback = notification_callback
        self._scan_thread = None
        self.comports = []
        self._is_on = False

    def start(self, reset: bool = False):
        if reset:
            self.comports = []
        self._is_on = True
        self._scan_thread = Thread(target=self._scan_job, daemon=True)
        self._scan_thread.start()

    def stop(self):
        self._is_on = False
        self._scan_thread.join()

    def _scan_job(self):

        cp_monitor = USBMonitor(filter_devices=([{'ID_VENDOR_ID': '10C4', 'ID_MODEL_ID': 'EA60'}]))

        while self._is_on:
            # Update COM ports
            com_port_list = serial.tools.list_ports.comports()

            # Specific VIP-PID devices
            for com_port in com_port_list:
                #if 'Silicon Lab' in str(com_port.manufacturer):
                # if 'VID:PID=10C4:EA60' in str(com_port.hwid):
                #     if com_port.name not in self.comports:
                #         logger.info('New REDRCP reader found: ' + com_port.name)
                #         self.comports.append(com_port.name)
                #         self.notification_callback(SenseidReaderConnectionInfo(driver=SupportedSenseidReader.REDRCP,
                #                                                                connection_string=com_port.name))
                # NUR
                #if 'NUR Module' in str(com_port.manufacturer):
                if 'VID:PID=04E6:0112' in str(com_port.hwid):
                    if com_port.name not in self.comports:
                        logger.info('New NUR reader found: ' + com_port.name)
                        self.comports.append(com_port.name)
                        self.notification_callback(SenseidReaderConnectionInfo(driver=SupportedSenseidReader.NURAPI,
                                                                               connection_string=com_port.name))
                        self.notification_callback(SenseidReaderConnectionInfo(driver=SupportedSenseidReader.NURAPY,
                                                                               connection_string=com_port.name))

            # CP based COM, with devide name in Serial String
            if platform.system() == 'Windows':
                cp_device_dict = cp_monitor.get_available_devices()
                for cp_device in cp_device_dict:
                    info = cp_device_dict[cp_device]
                    # SBLE-LCR
                    if info['ID_SERIAL'].startswith('KL-SBLE-LCR'):
                        port = info['ID_MODEL'].split('(')[-1].strip(')')
                        if port not in self.comports:
                            logger.info('New KL-SBLE-LCR found: ' + port
                                        + ' (SN:' + info['ID_SERIAL']
                                        + ')')
                            self.comports.append(port)
                            self.notification_callback(SenseidReaderConnectionInfo(driver=SupportedSenseidReader.KLSBLELCR,
                                                                                   connection_string=port))
            else:
                for com_port in com_port_list:
                    if 'KL-SBLE-LCR' in str(com_port.serial_number):
                        if com_port.device not in self.comports:
                            logger.info('New SBLE-LCR found: ' + com_port.product
                                        + ' (SN:' + com_port.serial_number
                                        + ')')
                            self.comports.append(com_port.device)
                            self.notification_callback(SenseidReaderConnectionInfo(driver=SupportedSenseidReader.KLSBLELCR,
                                                                                   connection_string=com_port.device))
            time.sleep(1)
