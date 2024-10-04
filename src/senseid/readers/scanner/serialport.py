import logging
import time
from threading import Thread
from typing import Callable

import serial
import serial.tools.list_ports

from .. import SenseidReaderConnectionInfo, SupportedSenseidReader

logger = logging.getLogger(__name__)


class SerialPortScanner:

    def __init__(self, notification_callback: Callable[[SenseidReaderConnectionInfo], None]):
        self.notification_callback = notification_callback
        self._scan_thread = Thread(target=self._scan_job, daemon=True)
        self._scan_thread.start()
        self.comports = []

    def _scan_job(self):
        while True:
            com_port_list = serial.tools.list_ports.comports()
            for com_port in com_port_list:
                # REDRCP
                if 'Silicon Lab' in str(com_port.manufacturer):
                    if com_port.name not in self.comports:
                        logger.info('New REDRCP reader found: ' + com_port.name)
                        self.comports.append(com_port.name)
                        self.notification_callback(SenseidReaderConnectionInfo(driver=SupportedSenseidReader.REDRCP,
                                                                               connection_string=com_port.name))
                # NUR
                if 'NUR Module' in str(com_port.manufacturer):
                    if com_port.name not in self.comports:
                        logger.info('New NUR reader found: ' + com_port.name)
                        self.comports.append(com_port.name)
                        self.notification_callback(SenseidReaderConnectionInfo(driver=SupportedSenseidReader.NURAPI,
                                                                               connection_string=com_port.name))
            time.sleep(1)
