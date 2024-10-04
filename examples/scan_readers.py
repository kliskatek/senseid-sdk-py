import logging
import time
from typing import List

from src.senseid.readers import SenseidReaderConnectionInfo
from src.senseid.readers.scanner import SenseidReaderScanner

logging.basicConfig(level=logging.DEBUG)


def scanner_notification_callback(reader_list: List[SenseidReaderConnectionInfo]):
    logging.info(reader_list)


scanner = SenseidReaderScanner(notification_callback=scanner_notification_callback)

time.sleep(5)
