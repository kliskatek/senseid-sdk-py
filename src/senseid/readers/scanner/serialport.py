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

    def __init__(self, notification_callback: Callable[[SenseidReaderConnectionInfo], None],
                 removal_callback: Callable[[SenseidReaderConnectionInfo], None] = None):
        self.notification_callback = notification_callback
        self.removal_callback = removal_callback
        self._scan_thread = None
        self.comports = {}  # port -> SenseidReaderConnectionInfo
        self._is_on = False

    def start(self, reset: bool = False):
        if reset:
            self.comports = {}
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
            current_ports = set()

            # Specific VIP-PID devices
            for com_port in com_port_list:
                # NUR
                if 'VID:PID=04E6:0112' in str(com_port.hwid):
                    current_ports.add(com_port.name)
                    if com_port.name not in self.comports:
                        logger.info('New NUR reader found: ' + com_port.name)
                        conn_info = SenseidReaderConnectionInfo(driver=SupportedSenseidReader.NURAPY,
                                                                connection_string=com_port.name)
                        self.comports[com_port.name] = conn_info
                        self.notification_callback(conn_info)

            # CP based COM, with device name in Serial String
            if platform.system() == 'Windows':
                cp_device_dict = cp_monitor.get_available_devices()
                for cp_device in cp_device_dict:
                    info = cp_device_dict[cp_device]
                    # SBLE-LCR
                    if info['ID_SERIAL'].startswith('KL-SBLE-LCR'):
                        port = info['ID_MODEL'].split('(')[-1].strip(')')
                        current_ports.add(port)
                        if port not in self.comports:
                            logger.info('New KL-SBLE-LCR found: ' + port
                                        + ' (SN:' + info['ID_SERIAL']
                                        + ')')
                            conn_info = SenseidReaderConnectionInfo(driver=SupportedSenseidReader.KLSBLELCR,
                                                                    connection_string=port)
                            self.comports[port] = conn_info
                            self.notification_callback(conn_info)
            else:
                for com_port in com_port_list:
                    if 'KL-SBLE-LCR' in str(com_port.serial_number):
                        current_ports.add(com_port.device)
                        if com_port.device not in self.comports:
                            logger.info('New SBLE-LCR found: ' + com_port.product
                                        + ' (SN:' + com_port.serial_number
                                        + ')')
                            conn_info = SenseidReaderConnectionInfo(driver=SupportedSenseidReader.KLSBLELCR,
                                                                    connection_string=com_port.device)
                            self.comports[com_port.device] = conn_info
                            self.notification_callback(conn_info)

            # Detect removed readers
            removed_ports = set(self.comports.keys()) - current_ports
            for port in removed_ports:
                logger.info('Reader disconnected: ' + port)
                conn_info = self.comports.pop(port)
                if self.removal_callback is not None:
                    self.removal_callback(conn_info)

            time.sleep(1)
