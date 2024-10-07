import logging
import time

from src.senseid.readers import SenseidReaderConnectionInfo, SupportedSenseidReader
from src.senseid.readers.scanner import SenseidReaderScanner

logging.basicConfig(level=logging.DEBUG)


def scanner_notification_callback(new_reader: SenseidReaderConnectionInfo):
    logging.info(new_reader)


# Scan readers with notifications
scanner = SenseidReaderScanner(notification_callback=scanner_notification_callback, autostart=True)

time.sleep(1)

# Get all readers found by the scanner
reader_list = scanner.get_readers()
logging.info(reader_list)

# Or wait until desired reader is found
nur_reader = scanner.wait_for_reader_of_type(reader_type=SupportedSenseidReader.NURAPI, timeout_s=1)
logging.info(nur_reader)
scanner.stop()
