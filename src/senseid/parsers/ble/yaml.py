import datetime
from dataclasses import dataclass
from enum import Enum
from importlib.resources import files
from typing import List, Dict

import yaml
from dataclasses_json import dataclass_json


class SenseidValueType(Enum):
    UINT8 = 'uint8'
    INT8 = 'int8'
    UINT16 = 'uint16'
    INT16 = 'int16'
    UINT16BE = 'uint16be'
    INT16BE = 'int16be'
    FLOAT = 'float'
    PADDING = 'padding'


class SenseidTransformType(Enum):
    NONE = 'none'
    LINEAR = 'linear'
    THERMISTOR_BETA = 'thermistor-beta'


@dataclass_json
@dataclass
class SenseidBleDataDef:
    magnitude: str
    unit_long: str
    unit_short: str
    type: SenseidValueType
    transform: SenseidTransformType
    coefficients: List[float]


@dataclass_json
@dataclass
class SenseidBleTypeDef:
    name: str
    description: str
    data_def: List[SenseidBleDataDef]
    fw_versions: List[int]


@dataclass_json
@dataclass
class SenseidBleDef:
    version: int
    date: datetime.date
    local_name: str
    types: Dict[int, SenseidBleTypeDef]


# Detect Source or Package mode
top_package = __name__.split('.')[0]
if top_package == 'src':
    senseid_package = files('src.senseid')
else:
    senseid_package = files('senseid')
_senseid_yaml = senseid_package.joinpath('definitions').joinpath('senseid_ble.yaml').read_text()
_senseid_dict = yaml.safe_load(_senseid_yaml)
SENSEID_BLE_DEF: SenseidBleDef = SenseidBleDef.from_dict(_senseid_dict)
