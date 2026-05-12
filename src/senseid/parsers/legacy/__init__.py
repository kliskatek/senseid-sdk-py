import logging
import struct
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from dataclasses_json import dataclass_json

from .yaml import SENSEID_LEGACY_DEF
from ..rain.yaml import SenseidTransformType, SenseidValueType
from .. import SenseidData, SenseidTag, SenseidTechnologies

logger = logging.getLogger(__name__)


@dataclass_json
@dataclass
class SenseidLegacyTag(SenseidTag):
    """RAIN tag whose sensor payload lives in User memory (Kliskatek legacy
    Rocky100-based tags). EPC is SenseID-style; data is decoded from the
    `user_mem_hex` blob obtained via inventory + embedded Read on USER bank.
    """

    def __init__(self, epc: str | bytearray, user_mem_hex: Optional[str | bytearray] = None):
        self.technology = SenseidTechnologies.RAIN
        self.timestamp = datetime.now()
        self.parse(epc, user_mem_hex)

    @staticmethod
    def _to_bytearray(value: str | bytearray | None) -> Optional[bytearray]:
        if value is None:
            return None
        if isinstance(value, bytearray):
            return value
        if isinstance(value, str):
            try:
                return bytearray.fromhex(value)
            except Exception:
                raise TypeError('value must be a hex string or bytearray')
        raise TypeError('value must be a hex string or bytearray')

    def _is_senseid_epc(self, epc_bytes: bytearray) -> bool:
        header_len = len(SENSEID_LEGACY_DEF.pen_header)
        if epc_bytes[0:header_len] != SENSEID_LEGACY_DEF.pen_header:
            return False
        # Legacy EPC layout: PEN(5) + type(1) + family_marker(1) + SN(5) = 12 B
        if len(epc_bytes) < header_len + 1 + 1 + 5:
            return False
        if epc_bytes[header_len + 1] != SENSEID_LEGACY_DEF.epc_family_marker:
            return False
        return True

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
        if fw_version_blob in SENSEID_LEGACY_DEF.skip_when.fw_version:
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

                self.data.append(SenseidData(
                    magnitude=data_config.magnitude,
                    magnitude_short=data_config.magnitude_short,
                    unit_long=data_config.unit_long,
                    unit_short=data_config.unit_short,
                    value=value,
                ))
        except Exception:
            logger.exception('Error decoding legacy user-memory datagram')
            self.data = None

    def parse(self, epc: str | bytearray, user_mem_hex: Optional[str | bytearray]):
        epc_bytes = self._to_bytearray(epc)
        user_mem = self._to_bytearray(user_mem_hex)
        self.id = epc_bytes.hex().upper()
        self.fw_version = None
        self.sn = None

        if not self._is_senseid_epc(epc_bytes):
            self.name = 'Rain ID'
            self.description = 'Standard Rain ID tag'
            self.datasheet_url = None
            self.store_url = None
            self.data = None
            return

        senseid_type = epc_bytes[5]
        self.sn = int.from_bytes(epc_bytes[7:12], 'big')
        self.id = epc_bytes[0:12].hex().upper()
        type_config = SENSEID_LEGACY_DEF.types.get(senseid_type)

        if type_config is None:
            self.name = 'Unknown legacy type'
            self.description = 'Unknown legacy type'
            self.datasheet_url = None
            self.store_url = None
            self.data = None
            return

        self.name = type_config.name
        self.description = type_config.description
        self.datasheet_url = type_config.datasheet_url
        self.store_url = type_config.store_url
        self._decode_user_mem(type_config, user_mem)
        logger.debug('Parsing legacy tag done -> %s', self)
