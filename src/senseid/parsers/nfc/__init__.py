import logging
from enum import Enum
from typing import List, Tuple, Optional

from .. import SenseidData, SenseidTag, SenseidTechnologies
from .yaml import SENSEID_NFC_DEF, SenseidNfcDataDef

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
    """Converts raw bytes into integers according to size and endianness."""
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


def parse_nfc_ndef(ndef_data: bytearray, uid: str = None) -> Tuple[Optional[SenseidTag], Optional[int]]:
    """Parse NDEF data into a SenseidTag + identified type_id.

    Returns (tag, type_id) where type_id is used for subsequent BULK parsing.
    Returns (None, None) if NDEF is invalid.
    """
    if ndef_data is None or len(ndef_data) < 11:
        logger.debug(f"NDEF packet too short: {len(ndef_data) if ndef_data else 0} bytes")
        return _unknown_tag(uid), None

    # Verify CC file (E1 40)
    if ndef_data[0] != 0xE1 or ndef_data[1] != 0x40:
        logger.debug(f"Invalid CC file: {ndef_data[0]:02X} {ndef_data[1]:02X}")
        return _unknown_tag(uid), None

    # Verify NDEF TLV
    if ndef_data[4] != 0x03:
        logger.debug(f"Invalid NDEF TLV: {ndef_data[4]:02X}")
        return _unknown_tag(uid), None

    # Verify type 'U' (URI)
    if ndef_data[9] != 0x55:
        logger.debug(f"NDEF type is not URI: {ndef_data[9]:02X}")
        return _unknown_tag(uid), None

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

    # Extract type_id and sensor data from URL
    # URL format: IP:PORT/VAL1,VAL2 -> use default_type
    # Future: IP:PORT/TYPE_HEX/VAL1,VAL2
    type_id, raw_values = _extract_type_and_values(url_part)

    type_def = SENSEID_NFC_DEF.types.get(type_id)
    if type_def is None:
        return _unknown_tag(uid), None

    data = _apply_data_def(raw_values, type_def.data_def) if raw_values else None

    tag = SenseidTag(
        technology=SenseidTechnologies.NFC,
        fw_version=None,
        sn=None,
        id=uid or '',
        name=type_def.name,
        description=type_def.description,
        data=data,
        datasheet_url=type_def.datasheet_url,
        store_url=type_def.store_url
    )
    logger.debug(f'NDEF parsed -> {tag}')
    return tag, type_id


def parse_nfc_bulk_sample(raw_values: list, sample_index: int,
                          type_id: int, uid: str = None) -> Optional[SenseidTag]:
    """Parse a single bulk sample (one group of N values) into a SenseidTag.

    raw_values: list of raw integer values for this sample (e.g., [temp_raw, hum_raw])
    type_id: sensor type identified from previous NDEF read
    """
    type_def = SENSEID_NFC_DEF.types.get(type_id)
    if type_def is None:
        return None

    data = _apply_data_def(raw_values, type_def.data_def)

    return SenseidTag(
        technology=SenseidTechnologies.NFC,
        fw_version=None,
        sn=None,
        id=uid or '',
        name=type_def.name,
        description=f'{type_def.description} (sample {sample_index})',
        data=data,
        datasheet_url=type_def.datasheet_url,
        store_url=type_def.store_url
    )


def _extract_type_and_values(url_part: str) -> Tuple[int, Optional[List[int]]]:
    """Extract sensor type ID and raw values from URL data part.

    Current format: IP:PORT/VAL1,VAL2 -> returns (default_type, [VAL1, VAL2])
    Future format:  IP:PORT/TYPE_HEX/VAL1,VAL2 -> returns (type_id, [VAL1, VAL2])
    """
    try:
        # Data is in the URL fragment: path.html#VAL1,VAL2
        if '#' in url_part:
            fragment = url_part.split('#', 1)[1]
            values = [int(v) for v in fragment.split(',')]
            return SENSEID_NFC_DEF.default_type, values

        if '/' not in url_part:
            return SENSEID_NFC_DEF.default_type, None

        parts = url_part.split('/')
        data_part = parts[-1]

        # Check if there's an explicit type in the URL (future format)
        if len(parts) >= 3:
            try:
                type_id = int(parts[-2], 16)
                if type_id in SENSEID_NFC_DEF.types:
                    values = [int(v) for v in data_part.split(',')]
                    return type_id, values
            except (ValueError, IndexError):
                pass

        # Legacy format: IP:PORT/VAL1,VAL2
        if ',' in data_part:
            values = [int(v) for v in data_part.split(',')]
            return SENSEID_NFC_DEF.default_type, values

    except (ValueError, IndexError) as e:
        logger.debug(f"Error extracting sensor data: {e}")

    return SENSEID_NFC_DEF.default_type, None


def _apply_data_def(raw_values: list, data_defs: List[SenseidNfcDataDef]) -> List[SenseidData]:
    """Apply YAML data_def transforms to raw values. Shared by NDEF and BULK."""
    result = []
    for i, data_def in enumerate(data_defs):
        if i >= len(raw_values):
            break
        value = data_def.coefficients[0] + data_def.coefficients[1] * raw_values[i]
        result.append(SenseidData(
            magnitude=data_def.magnitude,
            magnitude_short=data_def.magnitude_short,
            unit_long=data_def.unit_long,
            unit_short=data_def.unit_short,
            value=value
        ))
    return result


def _unknown_tag(uid: str = None) -> SenseidTag:
    """Create a SenseidTag for an unknown/unparseable NFC tag."""
    return SenseidTag(
        technology=SenseidTechnologies.NFC,
        fw_version=None,
        sn=None,
        id=uid or '',
        name='NFC Tag',
        description='Unknown NFC tag',
        data=None
    )
