import logging
import logging.config
import time

from src.senseid.parsers import SenseidTag
from src.senseid.readers import SupportedSenseidReader, create_SenseidReader
from src.senseid.readers.scanner import SenseidReaderScanner

logging.basicConfig(level=logging.INFO)

scanner = SenseidReaderScanner(autostart=True)
connection_info = scanner.wait_for_reader_of_type(SupportedSenseidReader.NURAPI, timeout_s=5)

if connection_info is None:
    print('No reader found')
    exit()

sid_reader = create_SenseidReader(connection_info)
sid_reader.connect(connection_info.connection_string)
#sid_reader.driver.SetLogLevel(NUR_LOG.NUR_LOG_ALL)

logging.info('Setting antenna configuration')
sid_reader.set_antenna_config(antenna_config_array=[True])
sid_reader.get_antenna_config()

logging.info('Setting valid TX power')
sid_reader.set_tx_power(15)
sid_reader.get_tx_power()
logging.info('Setting too low TX power')
sid_reader.set_tx_power(sid_reader.get_details().min_tx_power - 10)
sid_reader.get_tx_power()
logging.info('Setting too high TX power')
sid_reader.set_tx_power(sid_reader.get_details().max_tx_power + 10)
sid_reader.get_tx_power()

logging.info('Setting max TX power')
sid_reader.set_tx_power(sid_reader.get_details().max_tx_power)
sid_reader.get_tx_power()

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
time.sleep(1)

logging.info('Stopping inventory')
sid_reader.stop_inventory_async()

logging.info('Disconnecting from reader')
sid_reader.disconnect()
