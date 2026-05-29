import logging
import struct
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from dataclasses_json import dataclass_json

from .yaml import SENSEID_SENSEREAD_DEF
from ..rain.yaml import SenseidTransformType, SenseidValueType
from .. import SenseidData, SenseidTag, SenseidTechnologies

logger = logging.getLogger(__name__)


def is_senseid_senseread_epc(epc_bytes: bytes | bytearray) -> bool:
    """Return True if ``epc_bytes`` looks like a Kliskatek senseRead tag.

    senseRead tags share the SenseID PEN header AND type numbering with standard
    SenseID tags (e.g. 0x05 = RHAT for both). They are told apart by the family
    marker at byte 6 (the epc_version position): a senseRead tag carries
    ``SENSEID_SENSEREAD_DEF.epc_family_marker`` (0xFF) there, while a standard
    SenseID tag carries a real fw_version. The real firmware version of a
    senseRead tag lives in the User-memory datagram instead.
    """
    if epc_bytes is None:
        return False
    pen = SENSEID_SENSEREAD_DEF.pen_header
    marker_offset = len(pen) + 1  # byte 6
    if len(epc_bytes) <= marker_offset:
        return False
    if epc_bytes[0:len(pen)] != pen:
        return False
    return epc_bytes[marker_offset] == SENSEID_SENSEREAD_DEF.epc_family_marker


@dataclass_json
@dataclass
class SenseidSenseReadTag(SenseidTag):
    """RAIN tag whose sensor payload lives in User memory (Kliskatek senseRead
    Rocky100-based tags). EPC layout::

        bytes 0-4  : PEN header (00 00 00 F1 D3)
        byte  5    : type (same numbering as senseid_rain.yaml, e.g. 0x05 = RHAT)
        byte  6    : epc_family_marker (0xFF — marks the tag as senseRead; standard
                     SenseID carries a real fw_version here; real senseRead
                     fw_version lives in the User-memory datagram)
        bytes 7-11 : SN (5 bytes, big-endian)

    Sensor data is decoded from the ``user_mem_hex`` blob obtained via
    inventory + embedded Read on the USER bank.
    """

    def __init__(self, epc: str | bytearray, user_mem_hex: Optional[str | bytearray] = None):
        self.technology = SenseidTechnologies.RAIN
        self.timestamp = datetime.now()
        self.parse(epc, user_mem_hex)

    @staticmethod
    def _to_bytearray(value) -> Optional[bytearray]:
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray)):
            return bytearray(value)
        if isinstance(value, str):
            try:
                return bytearray.fromhex(value)
            except Exception:
                logger.debug('Could not parse hex string: %r', value[:40])
                return None
        logger.debug('Unsupported value type for senseRead parse: %s', type(value).__name__)
        return None

    def _is_senseread_epc(self, epc_bytes: bytearray) -> bool:
        # Full 12-byte check: PEN + type known + length enough for version + 5 B SN.
        if not is_senseid_senseread_epc(epc_bytes):
            return False
        header_len = len(SENSEID_SENSEREAD_DEF.pen_header)
        # PEN(5) + type(1) + version(1) + SN(5) = 12 bytes
        return len(epc_bytes) >= header_len + 1 + 1 + 5

    def _decode_user_mem(self, type_config, user_mem: bytearray):
        """Decode sensor values from the User-memory datagram.

        Layout:
          byte 0   : fw_version (uint8) — versions the datagram format
          bytes 1+ : sensor data per type.data_def (little-endian)
          last byte: QoS byte appended by R100 (ignored)
        """
        if user_mem is None or len(user_mem) < 1:
            self.data = None
            return

        fw_version_blob = user_mem[0]
        if fw_version_blob in SENSEID_SENSEREAD_DEF.skip_when.fw_version:
            # SPI buffer not refreshed yet, datagram is stale/invalid.
            self.data = None
            return

        self.fw_version = fw_version_blob
        payload = user_mem[1:]
        self.data = []
        try:
            for data_config in type_config.data_def:
                value_raw = None
                if data_config.type == SenseidValueType.UINT16:
                    value_raw = struct.unpack('<H', payload[:2])[0]
                    payload = payload[2:]
                elif data_config.type == SenseidValueType.INT16:
                    value_raw = struct.unpack('<h', payload[:2])[0]
                    payload = payload[2:]
                elif data_config.type == SenseidValueType.FLOAT:
                    value_raw = struct.unpack('<f', payload[:4])[0]
                    payload = payload[4:]

                value = None
                if value_raw is not None:
                    if data_config.transform == SenseidTransformType.NONE:
                        value = value_raw
                    elif data_config.transform == SenseidTransformType.LINEAR:
                        value = data_config.coefficients[0] + data_config.coefficients[1] * value_raw

                # Range check on the calibrated value (after transform).
                if (value is not None and data_config.valid_range
                        and not (data_config.valid_range[0] <= value <= data_config.valid_range[1])):
                    logger.debug('senseRead %s out of range: %s not in %s',
                                 data_config.magnitude, value, data_config.valid_range)
                    self.data = None
                    return

                self.data.append(SenseidData(
                    magnitude=data_config.magnitude,
                    magnitude_short=data_config.magnitude_short,
                    unit_long=data_config.unit_long,
                    unit_short=data_config.unit_short,
                    value=value,
                ))
        except Exception:
            logger.exception('Error decoding senseRead user-memory datagram')
            self.data = None

    def parse(self, epc: str | bytearray, user_mem_hex: Optional[str | bytearray]):
        epc_bytes = self._to_bytearray(epc)
        user_mem = self._to_bytearray(user_mem_hex)
        self.fw_version = None
        self.sn = None
        if epc_bytes is None:
            self.id = ''
            self.name = 'Rain ID'
            self.description = 'Standard Rain ID tag'
            self.datasheet_url = None
            self.store_url = None
            self.data = None
            return
        self.id = epc_bytes.hex().upper()

        if not self._is_senseread_epc(epc_bytes):
            self.name = 'Rain ID'
            self.description = 'Standard Rain ID tag'
            self.datasheet_url = None
            self.store_url = None
            self.data = None
            return

        senseid_type = epc_bytes[5]
        # byte 6 is the family marker (0xFF), already checked in
        # is_senseid_senseread_epc. The real fw_version lives in the User-memory
        # datagram, not the EPC.
        self.sn = int.from_bytes(epc_bytes[7:12], 'big')
        self.id = epc_bytes[0:12].hex().upper()
        type_config = SENSEID_SENSEREAD_DEF.types.get(senseid_type)

        if type_config is None:
            self.name = 'Unknown senseRead type'
            self.description = 'Unknown senseRead type'
            self.datasheet_url = None
            self.store_url = None
            self.data = None
            return

        self.name = type_config.name
        self.description = type_config.description
        self.datasheet_url = type_config.datasheet_url
        self.store_url = type_config.store_url
        self._decode_user_mem(type_config, user_mem)
        logger.debug('Parsing senseRead tag done -> %s', self)
