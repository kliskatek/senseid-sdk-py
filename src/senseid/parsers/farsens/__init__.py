import logging
import math
import struct
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from dataclasses_json import dataclass_json

from .yaml import SENSEID_FARSENS_DEF
from ..rain.yaml import SenseidTransformType, SenseidValueType
from .. import SenseidData, SenseidTag, SenseidTechnologies

logger = logging.getLogger(__name__)


@dataclass_json
@dataclass
class SenseidFarsensTag(SenseidTag):
    """RAIN tag from the Farsens family (Rocky100/102-based). Identified by
    EPC PEN `00 00 00 A9 3C` + 5-byte big-endian productId. Sensor payload
    lives in User memory (USER@0x100), starting with preamble 0xAA followed
    by fw_version and a model-specific blob (typically float32 LE values).
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
        logger.debug('Unsupported value type for Farsens parse: %s', type(value).__name__)
        return None

    def _is_farsens_epc(self, epc_bytes: bytearray) -> bool:
        header_len = len(SENSEID_FARSENS_DEF.pen_header)
        if epc_bytes[0:header_len] != SENSEID_FARSENS_DEF.pen_header:
            return False
        # PEN(5) + productId(5) = 10 bytes minimum
        if len(epc_bytes) < header_len + 5:
            return False
        return True

    def _decode_user_mem(self, type_config, user_mem: bytearray):
        data_index = SENSEID_FARSENS_DEF.data_index
        if user_mem is None or len(user_mem) < data_index:
            self.data = None
            return

        if user_mem[0] != SENSEID_FARSENS_DEF.preamble:
            # Invalid datagram (R100 SPI not armed yet, or wrong tag layout).
            self.data = None
            return

        self.fw_version = user_mem[1]
        payload = user_mem[data_index:]
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
                    elif data_config.transform == SenseidTransformType.LDR:
                        # uint16 LE packed as: bits 15..12 = exponent,
                        # bits 11..0 = fraction. Real value = c * 2^exp * frac.
                        exp = (int(value_raw) >> 12) & 0x0F
                        frac = int(value_raw) & 0x0FFF
                        c = data_config.coefficients[0] if data_config.coefficients else 1.0
                        value = c * (2 ** exp) * frac
                    elif data_config.transform == SenseidTransformType.THERMISTOR_BETA:
                        # Farsens reports thermistor resistance directly as a
                        # float32; SenseID standard tags ship a 12-bit ADC
                        # value from a 10kΩ half-bridge that needs unbridging
                        # first. Steinhart-Hart simplified is identical in
                        # both cases once R is known.
                        if data_config.type == SenseidValueType.FLOAT:
                            r_thermistor = value_raw
                        else:
                            r_thermistor = value_raw * 10e3 / (4095 - value_raw)
                        beta = data_config.coefficients[0]
                        r0 = data_config.coefficients[1]
                        t0 = data_config.coefficients[2] + 273.15
                        value = 1 / (1 / t0 + 1 / beta * math.log(r_thermistor / r0)) - 273.15

                # Range check on the calibrated value (after transform).
                if (value is not None and data_config.valid_range
                        and not (data_config.valid_range[0] <= value <= data_config.valid_range[1])):
                    logger.debug('farsens %s out of range: %s not in %s',
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
            logger.exception('Error decoding Farsens user-memory datagram')
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

        if not self._is_farsens_epc(epc_bytes):
            self.name = 'Rain ID'
            self.description = 'Standard Rain ID tag'
            self.datasheet_url = None
            self.store_url = None
            self.data = None
            return

        # productId: 5 bytes after the PEN, big-endian.
        product_id = int.from_bytes(epc_bytes[5:10], 'big')
        # SN: anything after the productId (factory-unique).
        self.sn = int.from_bytes(epc_bytes[10:], 'big') if len(epc_bytes) > 10 else None
        self.id = epc_bytes.hex().upper()

        type_config = SENSEID_FARSENS_DEF.types.get(product_id)
        if type_config is None:
            self.name = 'Unknown Farsens type'
            self.description = f'Unknown Farsens productId 0x{product_id:02X}'
            self.datasheet_url = None
            self.store_url = None
            self.data = None
            return

        self.name = type_config.name
        self.description = type_config.description
        self.datasheet_url = type_config.datasheet_url
        self.store_url = type_config.store_url
        self._decode_user_mem(type_config, user_mem)
        logger.debug('Parsing Farsens tag done -> %s', self)
