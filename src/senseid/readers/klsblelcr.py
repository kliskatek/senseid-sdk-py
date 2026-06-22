import logging
import struct
from typing import List, Callable

from driver_sble_py_klsblelcf import KlSbleLcr

from . import SenseidReader, SenseidReaderDetails
from ..parsers import SenseidTag, SenseidTechnologies
from ..parsers.ble import SenseidBleTag

logger = logging.getLogger(__name__)


class SenseidKlSbleLcr(SenseidReader):

    technology = SenseidTechnologies.BLE

    def __init__(self):
        self.details = None
        self.driver = KlSbleLcr()
        self.notification_callback = None
        self.tx_power = 0

    def connect(self, connection_string: str):
        self.driver.connect(connection_string=connection_string)
        self.driver.set_notification_callback(self._sble_notification_callback)
        return True

    def _sble_notification_callback(self, beacon):
        if self.notification_callback is not None:
            self.notification_callback(SenseidBleTag(beacon))
        pass

    def disconnect(self):
        self.driver.disconnect()

    def get_details(self) -> SenseidReaderDetails:
        if self.details is None:
            self.details = SenseidReaderDetails(
                model_name='KL-SBLE-LCR',
                region='EU',
                firmware_version='1.0.0',
                antenna_count=1,
                min_tx_power=10,
                max_tx_power=31.5
            )
            logger.debug(self.details)
        return self.details

    def get_tx_power(self) -> float:
        response = self.driver.get_tx_power()
        if isinstance(response, (bytes, bytearray)) and len(response) >= 2:
            raw = struct.unpack('>H', response[:2])[0]
            return raw / 10.0
        return float(response)

    def set_tx_power(self, dbm: float):
        return self.driver.set_tx_power(dbm)

    def get_antenna_config(self) -> List[bool]:
        antenna_config_array = [True]
        return antenna_config_array

    def set_antenna_config(self, antenna_config_array: List[bool]):
        logger.debug('Antenna configuration is fixed')

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None],
                              error_callback=None):
        self.notification_callback = notification_callback
        return self.driver.start()

    def stop_inventory_async(self):
        return self.driver.stop()

    def set_rf_channel(self, channel: int | None) -> bool:
        """Lock CW to a single RF channel (certification mode).

        None restores frequency hopping (default); 0..3 fixes the reader
        to one of the four Europe-868 channels (865.7 / 866.3 / 866.9 /
        867.5 MHz). The setting is volatile — a power-cycle or RESET_*
        on the reader brings it back to hopping.
        """
        return self.driver.set_cw_channel(channel)

    # -- Certification test signals (EN 302 208) --

    def start_cw(self) -> bool:
        """Emit an unmodulated carrier (CW) on the selected channel.

        Isolated CW for certification: unlike start_inventory_async() this
        does not start the BLE receiver. Lock the channel first with
        set_rf_channel().
        """
        return self.driver.start_cw()

    def stop_cw(self) -> bool:
        """Stop the unmodulated carrier."""
        return self.driver.stop_cw()

    def start_test_signal(self, on_ms: int = 30, off_ms: int = 5) -> bool:
        """Start the modulated test signal (succession of transmit pulses).

        on_ms (10..50) of modulated carrier followed by off_ms (1..10) of
        silence, repeated until stop_test_signal(). Lock the channel first
        with set_rf_channel().
        """
        return self.driver.start_test_signal(on_ms, off_ms)

    def stop_test_signal(self) -> bool:
        """Stop the modulated test signal pulse train."""
        return self.driver.stop_test_signal()
