import logging
import struct
from dataclasses import dataclass
from math import log

from dataclasses_json import dataclass_json

from .yaml import SENSEID_BLE_DEF, SenseidValueType, SenseidTransformType
from .. import SenseidData, SenseidTag, SenseidTechnologies

logger = logging.getLogger(__name__)


@dataclass_json
@dataclass
class SenseidBleTag(SenseidTag):

    def __init__(self, beacon: str | bytearray):
        self.technology = SenseidTechnologies.BLE
        self.parse_beacon(beacon)

    def _get_bytearray_beacon(self, beacon: str | bytearray):
        if not (isinstance(beacon, str) or isinstance(beacon, bytearray)):
            raise TypeError('epc must be a hex string or bytearray')
        if isinstance(beacon, str):
            try:
                return bytearray.fromhex(beacon)
            except Exception as e:
                raise TypeError('epc must be a hex string or bytearray')
        return beacon

    def _is_senseid_beacon(self, beacon_bytes: bytearray):
        try:
            local_name = beacon_bytes[6+2:len(SENSEID_BLE_DEF.local_name)+6+2]
            if local_name.decode() != SENSEID_BLE_DEF.local_name:
                return False
            if len(beacon_bytes) < len(SENSEID_BLE_DEF.local_name) + 2 + 3:  # PEN + TYPE + SN
                return False
            return True
        except Exception as e:
            return False

    def _parse_senseid_beacon(self, beacon_bytes: bytearray):
        senseid_type = beacon_bytes[6+8]
        fw_version = beacon_bytes[6+9]
        #senseid_sn_bytes = beacon_bytes[7:10]
        id = beacon_bytes[0:6].hex(sep=':').upper()

        #sn = struct.unpack('>I', bytearray([0]) + senseid_sn_bytes)[0]
        sn = 0
        if senseid_type not in SENSEID_BLE_DEF.types:
            self.id = 'ID'
            self.fw_version = None
            self.sn = None
            self.name = 'Unknown SenseID type'
            self.description = 'Unknown SenseID type'
            self.data = None
            return

        senseid_value_bytes = beacon_bytes[6+10:]
        senseid_type_config = SENSEID_BLE_DEF.types[senseid_type]
        self.id = id
        self.fw_version = fw_version
        self.sn = sn
        self.name = senseid_type_config.name
        self.description = senseid_type_config.description
        self.data = []
        try:
            for data_config in senseid_type_config.data_def:
                value_raw = None
                if data_config.type == SenseidValueType.PADDING:
                    senseid_value_bytes = senseid_value_bytes[1:]
                    continue
                if data_config.type == SenseidValueType.UINT16:
                    value_raw = struct.unpack('<H', senseid_value_bytes[:2])[0]
                    senseid_value_bytes = senseid_value_bytes[2:]
                if data_config.type == SenseidValueType.INT16:
                    value_raw = struct.unpack('<h', senseid_value_bytes[:2])[0]
                    senseid_value_bytes = senseid_value_bytes[2:]
                if data_config.type == SenseidValueType.UINT16BE:
                    value_raw = struct.unpack('>H', senseid_value_bytes[:2])[0]
                    senseid_value_bytes = senseid_value_bytes[2:]
                if data_config.type == SenseidValueType.INT16BE:
                    value_raw = struct.unpack('>h', senseid_value_bytes[:2])[0]
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

    def parse_beacon(self, beacon: str | bytearray):
        beacon_bytes = self._get_bytearray_beacon(beacon)
        if self._is_senseid_beacon(beacon_bytes):
            self._parse_senseid_beacon(beacon_bytes)
        else:
            self.id = beacon_bytes.hex().upper()
            self.fw_version = None
            self.sn = None
            self.name = 'BLE beacon'
            self.description = 'Standard BLE beacon'
            self.data = None
        logger.debug('Parsing done -> ' + str(self))
