import logging
import time
from threading import Thread
from typing import Callable

from smartcard.System import readers

from .. import SenseidReaderConnectionInfo, SupportedSenseidReader

logger = logging.getLogger(__name__)


class PcscScanner:

    def __init__(self, notification_callback: Callable[[SenseidReaderConnectionInfo], None],
                 removal_callback: Callable[[SenseidReaderConnectionInfo], None] = None):
        self.notification_callback = notification_callback
        self.removal_callback = removal_callback
        self._scan_thread = None
        self.found_readers = {}  # reader_name -> SenseidReaderConnectionInfo
        self._is_on = False

    def start(self, reset: bool = False):
        if reset:
            self.found_readers = {}
        self._is_on = True
        self._scan_thread = Thread(target=self._scan_job, daemon=True)
        self._scan_thread.start()

    def stop(self):
        self._is_on = False
        if self._scan_thread is not None:
            self._scan_thread.join()

    def _scan_job(self):
        while self._is_on:
            try:
                pcsc_readers = readers()
                current_readers = set()
                for reader in pcsc_readers:
                    reader_name = str(reader)
                    if 'ACR1552' in reader_name and 'PICC' in reader_name:
                        current_readers.add(reader_name)
                        if reader_name not in self.found_readers:
                            logger.info('New ACR1552 reader found: ' + reader_name)
                            conn_info = SenseidReaderConnectionInfo(
                                driver=SupportedSenseidReader.ACR1552,
                                connection_string=reader_name
                            )
                            self.found_readers[reader_name] = conn_info
                            self.notification_callback(conn_info)
                # Detect removed readers
                removed_readers = set(self.found_readers.keys()) - current_readers
                for reader_name in removed_readers:
                    logger.info('ACR1552 reader disconnected: ' + reader_name)
                    conn_info = self.found_readers.pop(reader_name)
                    if self.removal_callback is not None:
                        self.removal_callback(conn_info)
            except Exception as e:
                logger.debug(f"PC/SC scan error: {e}")
            time.sleep(1)