import logging
import logging.config
import time

from src.senseid.parsers import SenseidTag
from src.senseid.readers import SupportedSenseidReader, create_SenseidReader
from src.senseid.readers.scanner import SenseidReaderScanner

logging.basicConfig(level=logging.DEBUG)

scanner = SenseidReaderScanner()

time.sleep(1)
connection_info = None
for reader_connection_info in scanner.get_readers():
    if reader_connection_info.driver == SupportedSenseidReader.NURAPI:
        connection_info = reader_connection_info
        break

if connection_info is None:
    print('No reader found')
    exit()

sid_reader = create_SenseidReader(connection_info)
sid_reader.connect(connection_info.connection_string)
sid_reader.set_tx_power(dbm=20)
tx_power = sid_reader.get_tx_power()
logging.info(tx_power)
sid_reader.set_tx_power(dbm=sid_reader.get_details().max_tx_power + 1)
tx_power = sid_reader.get_tx_power()
logging.info(tx_power)


def notification_callback(epc: SenseidTag):
    logging.info(epc)


logging.info('Starting inventory')
sid_reader.start_inventory_async(notification_callback=notification_callback)
input()
time.sleep(1)

logging.info('Stopping inventory')
sid_reader.stop_inventory_async()

logging.info('Disconnecting from reader')
sid_reader.disconnect()
