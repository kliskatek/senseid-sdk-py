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
    FLOAT = 'float'


class SenseidTransformType(Enum):
    NONE = 'none'
    LINEAR = 'linear'


@dataclass_json
@dataclass
class SenseidNfcDataDef:
    magnitude: str
    magnitude_short: str
    unit_long: str
    unit_short: str
    type: SenseidValueType
    transform: SenseidTransformType
    coefficients: List[float]


@dataclass_json
@dataclass
class SenseidNfcTypeDef:
    name: str
    description: str
    data_def: List[SenseidNfcDataDef]


@dataclass_json
@dataclass
class SenseidNfcDef:
    version: int
    date: datetime.date
    default_type: int
    types: Dict[int, SenseidNfcTypeDef]


# Detect Source or Package mode
top_package = __name__.split('.')[0]
if top_package == 'src':
    senseid_package = files('src.senseid')
else:
    senseid_package = files('senseid')
_senseid_yaml = senseid_package.joinpath('definitions').joinpath('senseid_nfc.yaml').read_text()
_senseid_dict = yaml.safe_load(_senseid_yaml)
SENSEID_NFC_DEF: SenseidNfcDef = SenseidNfcDef.from_dict(_senseid_dict)
