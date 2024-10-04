import logging
import struct
from dataclasses import dataclass
from math import log

from dataclasses_json import dataclass_json

from .yaml import SENSEID_RAIN_DEF, SenseidValueType, SenseidTransformType
from .. import SenseidData, SenseidTag, SenseidTechnologies

logger = logging.getLogger(__name__)


@dataclass_json
@dataclass
class SenseidRainTag(SenseidTag):

    def __init__(self, epc: str | bytearray):
        self.technology = SenseidTechnologies.RAIN
        self.parse_epc(epc)

    def _get_bytearray_epc(self, epc: str | bytearray):
        if not (isinstance(epc, str) or isinstance(epc, bytearray)):
            raise TypeError('epc must be a hex string or bytearray')
        if isinstance(epc, str):
            try:
                return bytearray.fromhex(epc)
            except Exception as e:
                raise TypeError('epc must be a hex string or bytearray')
        return epc

    def _is_senseid_epc(self, epc_bytes: bytearray):
        pen_header = epc_bytes[0:len(SENSEID_RAIN_DEF.pen_header)]
        if pen_header != SENSEID_RAIN_DEF.pen_header:
            return False
        if len(epc_bytes) < len(SENSEID_RAIN_DEF.pen_header) + 2 + 3:  # PEN + TYPE + SN
            return False
        return True

    def _parse_senseid_epc(self, epc_bytes: bytearray):
        senseid_type_bytes = epc_bytes[5:7]
        senseid_sn_bytes = epc_bytes[7:10]
        id = epc_bytes[0:10].hex().upper()

        senseid_type = struct.unpack('>H', senseid_type_bytes)[0]
        if senseid_type not in SENSEID_RAIN_DEF.types:
            self.id = id
            self.name = 'Unknown SenseID type'
            self.description = 'Unknown SenseID type'
            self.data = None
            return

        senseid_value_bytes = epc_bytes[10:]
        senseid_type_config = SENSEID_RAIN_DEF.types[senseid_type]
        self.id = id
        self.name = senseid_type_config.name
        self.description = senseid_type_config.description
        self.data = []
        try:
            for data_config in senseid_type_config.data_def:
                value_raw = None
                if data_config.type == SenseidValueType.UINT16:
                    value_raw = struct.unpack('<H', senseid_value_bytes[:2])[0]
                    senseid_value_bytes = senseid_value_bytes[2:]
                if data_config.type == SenseidValueType.INT16:
                    value_raw = struct.unpack('<h', senseid_value_bytes[:2])[0]
                    senseid_value_bytes = senseid_value_bytes[2:]
                if data_config.type == SenseidValueType.FLOAT:
                    value_raw = struct.unpack('<f', senseid_value_bytes[:4])[0]
                    senseid_value_bytes = senseid_value_bytes[4:]

                value = None
                if value_raw is not None:
                    if data_config.transform == SenseidTransformType.NONE:
                        value = value_raw
                    if data_config.transform == SenseidTransformType.LINEAR:
                        value = data_config.coefficients[0] + data_config.coefficients[1] * value_raw
                    if data_config.transform == SenseidTransformType.THERMISTOR_BETA:
                        # value_raw is in adc12 value of 10k half bridge
                        r_thermistor = value_raw * 10e3 / (4095 - value_raw)
                        beta = data_config.coefficients[0]
                        r0 = data_config.coefficients[1]
                        t0 = data_config.coefficients[2] + 273.15
                        value = 1 / (1 / t0 + 1 / beta * log(r_thermistor / r0)) - 273.15

                data = SenseidData(magnitude=data_config.magnitude,
                                   unit_long=data_config.unit_long,
                                   unit_short=data_config.unit_short,
                                   value=value)
                self.data.append(data)
        except Exception as e:
            raise Exception("Error parsing senseid data")

    def parse_epc(self, epc: str | bytearray):
        epc_bytes = self._get_bytearray_epc(epc)
        if self._is_senseid_epc(epc_bytes):
            self._parse_senseid_epc(epc_bytes)
        else:
            self.id = epc_bytes.hex().upper()
            self.name = 'Rain ID'
            self.description = 'Standard Rain ID tag'
            self.data = None
        logger.debug('Parsing done -> ' + str(self))
