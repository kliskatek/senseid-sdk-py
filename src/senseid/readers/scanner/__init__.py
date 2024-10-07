import datetime
import logging
import time
from typing import List, Callable

from .. import SenseidReaderConnectionInfo, SupportedSenseidReader
from .multicast_dns_service_discovery import MulticastDnsServiceDiscoveryScanner
from .serialport import SerialPortScanner

logger = logging.getLogger(__name__)


class SenseidReaderScanner:

    def __init__(self, notification_callback: Callable[[SenseidReaderConnectionInfo], None] = None,
                 autostart: bool = False):
        logger.info('Starting Reader Scanner')
        self.notification_callback = notification_callback
        self.readers: List[SenseidReaderConnectionInfo] = []
        self.serial_port_scanner = SerialPortScanner(notification_callback=self._add_reader)
        self.multicast_dns_service_discovery_scanner = MulticastDnsServiceDiscoveryScanner(
            notification_callback=self._add_reader)
        if autostart:
            self.start()

    def start(self, reset: bool = False, notification_callback: Callable[[SenseidReaderConnectionInfo], None] = None):
        if reset:
            self.readers: List[SenseidReaderConnectionInfo] = []
        if notification_callback is not None:
            self.notification_callback = notification_callback

        self.serial_port_scanner.start(reset=reset)
        self.multicast_dns_service_discovery_scanner.start()

    def stop(self):
        self.serial_port_scanner.stop()
        self.multicast_dns_service_discovery_scanner.stop()

    def _add_reader(self, connection_info: SenseidReaderConnectionInfo):
        self.readers.append(connection_info)
        if self.notification_callback is not None:
            self.notification_callback(connection_info)

    def get_readers(self):
        return self.readers

    def _get_first_reader_connection_info_of_type(self, reader_type: SupportedSenseidReader):
        for reader_connection_info in self.readers:
            if reader_connection_info.driver == reader_type:
                return reader_connection_info

    def wait_for_reader_of_type(self, reader_type: SupportedSenseidReader, timeout_s=-1) -> SenseidReaderConnectionInfo:
        timestamp_timeout = (datetime.datetime.now() + datetime.timedelta(seconds=timeout_s)) if timeout_s > 0 else None
        while True:
            reader_connection_info = self._get_first_reader_connection_info_of_type(reader_type)
            if reader_connection_info is not None:
                return reader_connection_info
            time.sleep(0.1)
            if timestamp_timeout is not None:
                if datetime.datetime.now() > timestamp_timeout:
                    break
