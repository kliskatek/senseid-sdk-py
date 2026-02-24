import logging

from driver_snfc_py_acr1552.acr1552 import Acr1552

from . import SenseidReaderDetails
from ..parsers.nfc import SenseidNfcTag, convert_to_uint, Endianness

logger = logging.getLogger(__name__)


class SenseidAcr1552:

    NTAG5_NDEF_BASE_BLOCK = 0
    NTAG5_NDEF_HEADER_NBLOCKS = 2

    NTAG5_IDX_BLOCK = 50
    NTAG5_IDX_NBLOCKS = 1

    NTAG5_DATA_BASE_BLOCK = 0
    NTAG5_DATA_NBLOCKS = 50

    def __init__(self):
        self.driver = Acr1552()
        self.details = None

    def connect(self, connection_string: str = None):
        return self.driver.connect(connection_string=connection_string)

    def disconnect(self):
        self.driver.disconnect()

    def get_details(self) -> SenseidReaderDetails:
        if self.details is None:
            self.details = SenseidReaderDetails(
                model_name='ACR1552',
                region='EU',
                firmware_version='1.0.1',
                antenna_count=1,
                min_tx_power=0,
                max_tx_power=0
            )
        return self.details

    # -- Field control --

    def turn_on_field(self):
        return self.driver.set_power(True)

    def turn_off_field(self):
        return self.driver.set_power(False)

    # -- Mode control --

    def set_ndef_mode(self):
        return self.driver.change_fw_mode(False)

    def set_bulk_mode(self):
        return self.driver.change_fw_mode(True)

    # -- Tag operations --

    def get_uid(self):
        return self.driver.get_uid()

    def read_ndef(self, uid=None) -> SenseidNfcTag:
        # First read: get CC + NDEF TLV header to determine message length
        header = self.driver.read_data(self.NTAG5_NDEF_BASE_BLOCK, self.NTAG5_NDEF_HEADER_NBLOCKS)
        if header is None or len(header) < 6:
            return None
        # Verify CC (E1 40) and NDEF TLV type (03)
        if header[0] != 0xE1 or header[1] != 0x40 or header[4] != 0x03:
            return None
        # NDEF length at byte 5: total bytes = CC(4) + TLV type(1) + TLV length(1) + payload
        ndef_length = header[5]
        total_bytes = 4 + 1 + 1 + ndef_length
        total_blocks = (total_bytes + 3) // 4  # Round up to full blocks
        # Second read: get the full NDEF data
        data = self.driver.read_data(self.NTAG5_NDEF_BASE_BLOCK, total_blocks)
        if data is None:
            return None
        uid_str = bytearray(uid).hex().upper() if uid else None
        return SenseidNfcTag(bytearray(data), uid=uid_str)

    def read_tag_index(self):
        data = self.driver.read_data(self.NTAG5_IDX_BLOCK, self.NTAG5_IDX_NBLOCKS)
        idx_list = convert_to_uint(data, 4, Endianness.LITTLE.value)
        if idx_list:
            return idx_list[0]
        return None

    def read_bulk_data(self):
        data = self.driver.read_data(self.NTAG5_DATA_BASE_BLOCK, self.NTAG5_DATA_NBLOCKS)
        if data is None:
            return None
        return convert_to_uint(data, 2, Endianness.LITTLE.value)

    # -- Raw access --

    def read_data(self, start_block, n_blocks):
        return self.driver.read_data(start_block, n_blocks)

    def write_data(self, start_block, wdata):
        return self.driver.write_data(start_block, wdata)