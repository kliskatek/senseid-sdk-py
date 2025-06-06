import logging
import logging.config
import time

from src.senseid.parsers import SenseidTag
from src.senseid.readers import SupportedSenseidReader, create_SenseidReader
from src.senseid.readers.scanner import SenseidReaderScanner

logging.basicConfig(level=logging.DEBUG)

scanner = SenseidReaderScanner(autostart=True)
connection_info = scanner.wait_for_reader_of_type(SupportedSenseidReader.KLSBLELCR, timeout_s=5)

if connection_info is None:
    print('No reader found')
    exit()

sid_reader = create_SenseidReader(connection_info)
sid_reader.connect(connection_info.connection_string)

sid_reader.set_tx_power(15)

n_tags = 0
start = time.monotonic()


def notification_callback(tag: SenseidTag):
    global n_tags, start
    logging.info(tag)
    n_tags += 1
    print(n_tags/(time.monotonic() - start))


logging.info('Starting inventory')
sid_reader.start_inventory_async(notification_callback=notification_callback)

input()
time.sleep(3)

logging.info('Stopping inventory')
sid_reader.stop_inventory_async()

logging.info('Disconnecting from reader')
sid_reader.disconnect()
