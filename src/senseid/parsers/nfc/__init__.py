import logging
from dataclasses import dataclass
from enum import Enum

from dataclasses_json import dataclass_json

from .. import SenseidData, SenseidTag, SenseidTechnologies

logger = logging.getLogger(__name__)


class Endianness(Enum):
    LITTLE = False
    BIG = True


URI_PREFIXES = {
    0x00: "",
    0x01: "http://www.",
    0x02: "https://www.",
    0x03: "http://",
    0x04: "https://",
    0x05: "tel:",
    0x06: "mailto:",
    0x07: "ftp://anonymous:anonymous@",
    0x08: "ftp://ftp.",
    0x09: "ftps://",
    0x0A: "sftp://",
    0x0B: "smb://",
    0x0C: "nfs://",
    0x0D: "ftp://",
    0x0E: "dav://",
    0x0F: "news:",
    0x10: "telnet://",
    0x11: "imap:",
    0x12: "rtsp://",
    0x13: "urn:",
    0x14: "pop:",
    0x15: "sip:",
    0x16: "sips:",
    0x17: "tftp:",
    0x18: "btspp://",
    0x19: "btl2cap://",
    0x1A: "btgoep://",
    0x1B: "tcpobex://",
    0x1C: "irdaobex://",
    0x1D: "file://",
    0x1E: "urn:epc:id:",
    0x1F: "urn:epc:tag:",
    0x20: "urn:epc:pat:",
    0x21: "urn:epc:raw:",
    0x22: "urn:epc:",
    0x23: "urn:nfc:",
}


def convert_to_uint(data, uint_size, endianness):
    """
    Converts raw bytes into integers according to size and endianness.
    - data: bytearray or list of bytes
    - uint_size: number of bytes per integer (e.g. 2 for uint16, 4 for uint32)
    - endianness: True for big-endian, False for little-endian
    """
    if data is None:
        return None

    result = []
    for i in range(0, len(data), uint_size):
        byte_group = list(data[i:i + uint_size])
        if len(byte_group) < uint_size:
            break
        if endianness == Endianness.LITTLE.value:
            byte_group.reverse()
        value = 0
        for byte_val in byte_group:
            value = (value << 8) | byte_val
        result.append(value)

    return result


@dataclass_json
@dataclass
class SenseidNfcTag(SenseidTag):

    def __init__(self, ndef_data: bytearray, uid: str = None):
        self.technology = SenseidTechnologies.NFC
        self.parse_ndef(ndef_data, uid)

    def parse_ndef(self, ndef_data: bytearray, uid: str = None):
        if ndef_data is None or len(ndef_data) < 11:
            self._set_unknown(uid)
            logger.debug(f"NDEF packet too short: {len(ndef_data) if ndef_data else 0} bytes")
            return

        # Verify CC file (E1 40)
        if ndef_data[0] != 0xE1 or ndef_data[1] != 0x40:
            self._set_unknown(uid)
            logger.debug(f"Invalid CC file: {ndef_data[0]:02X} {ndef_data[1]:02X}")
            return

        # Verify NDEF TLV
        if ndef_data[4] != 0x03:
            self._set_unknown(uid)
            logger.debug(f"Invalid NDEF TLV: {ndef_data[4]:02X}")
            return

        # Verify type 'U' (URI)
        if ndef_data[9] != 0x55:
            self._set_unknown(uid)
            logger.debug(f"NDEF type is not URI: {ndef_data[9]:02X}")
            return

        # URI Identifier Code
        uri_prefix = URI_PREFIXES.get(ndef_data[10], "")

        # Extract payload (URL)
        payload_length = ndef_data[8]
        payload_start = 11
        payload_end = payload_start + payload_length - 1  # -1 because URI ID is already counted

        if payload_end > len(ndef_data):
            payload_end = len(ndef_data)

        url_part = ''.join(chr(b) for b in ndef_data[payload_start:payload_end] if b != 0xFE and b != 0x00)
        full_url = uri_prefix + url_part

        # Set tag identity
        self.id = uid or ''
        self.fw_version = None
        self.sn = None
        self.name = 'NFC NDEF Tag'
        self.description = full_url

        # Extract temperature and humidity from URL format: IP:PORT/TEMP,HUM
        self.data = self._parse_sensor_data(url_part)
        logger.debug('Parsing done -> ' + str(self))

    def _parse_sensor_data(self, url_part):
        try:
            if '/' in url_part:
                data_part = url_part.split('/')[-1]
                if ',' in data_part:
                    temp_str, hum_str = data_part.split(',')
                    temperature = int(temp_str) / 100.0
                    humidity = int(hum_str) / 100.0
                    return [
                        SenseidData(
                            magnitude='Temperature',
                            unit_long='Celsius',
                            unit_short='°C',
                            value=temperature
                        ),
                        SenseidData(
                            magnitude='Humidity',
                            unit_long='Percent',
                            unit_short='%',
                            value=humidity
                        ),
                    ]
        except (ValueError, IndexError) as e:
            logger.debug(f"Error extracting sensor data: {e}")
        return None

    def _set_unknown(self, uid):
        self.id = uid or ''
        self.fw_version = None
        self.sn = None
        self.name = 'NFC Tag'
        self.description = 'Unknown NFC tag'
        self.data = None
