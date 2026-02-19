import logging
import time
from threading import Thread
from typing import Callable

from smartcard.System import readers

from .. import SenseidReaderConnectionInfo, SupportedSenseidReader

logger = logging.getLogger(__name__)


class PcscScanner:

    def __init__(self, notification_callback: Callable[[SenseidReaderConnectionInfo], None]):
        self.notification_callback = notification_callback
        self._scan_thread = None
        self.found_readers = []
        self._is_on = False

    def start(self, reset: bool = False):
        if reset:
            self.found_readers = []
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
                for reader in pcsc_readers:
                    reader_name = str(reader)
                    if 'ACR1552' in reader_name and 'PICC' in reader_name:
                        if reader_name not in self.found_readers:
                            logger.info('New ACR1552 reader found: ' + reader_name)
                            self.found_readers.append(reader_name)
                            self.notification_callback(
                                SenseidReaderConnectionInfo(
                                    driver=SupportedSenseidReader.ACR1552,
                                    connection_string=reader_name
                                )
                            )
            except Exception as e:
                logger.debug(f"PC/SC scan error: {e}")
            time.sleep(1)