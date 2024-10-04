import logging
from typing import List, Callable


from .. import SenseidReaderConnectionInfo
from .multicast_dns_service_discovery import MulticastDnsServiceDiscoveryScanner
from .serialport import SerialPortScanner

logger = logging.getLogger(__name__)


class SenseidReaderScanner:

    def __init__(self, notification_callback: Callable[[List[SenseidReaderConnectionInfo]], None] = None):
        logger.info('Starting Reader Scanner')
        self.notification_callback = notification_callback
        self.readers: List[SenseidReaderConnectionInfo] = []
        SerialPortScanner(notification_callback=self._add_reader)
        MulticastDnsServiceDiscoveryScanner(notification_callback=self._add_reader)

    def _add_reader(self, connection_info: SenseidReaderConnectionInfo):
        self.readers.append(connection_info)
        if self.notification_callback is not None:
            self.notification_callback(self.readers)

    def get_readers(self):
        return self.readers
