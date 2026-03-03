import datetime
from dataclasses import dataclass, field
from enum import Enum
from importlib.resources import files
from typing import List, Dict, Optional

import yaml
from dataclasses_json import dataclass_json


class SenseidValueType(Enum):
    UINT16 = 'uint16'
    INT16 = 'int16'
    FLOAT = 'float'


class SenseidTransformType(Enum):
    NONE = 'none'
    LINEAR = 'linear'
    THERMISTOR_BETA = 'thermistor-beta'


@dataclass_json
@dataclass
class SenseidRainDataDef:
    magnitude: str
    magnitude_short: str
    unit_long: str
    unit_short: str
    type: SenseidValueType
    transform: SenseidTransformType
    coefficients: List[float]


@dataclass_json
@dataclass
class SenseidRainTypeDef:
    name: str
    description: str
    data_def: List[SenseidRainDataDef]
    fw_versions: List[int]
    datasheet_url: Optional[str] = field(default=None)
    store_url: Optional[str] = field(default=None)


@dataclass_json
@dataclass
class SenseidRainDef:
    version: int
    date: datetime.date
    pen_header: bytearray
    types: Dict[int, SenseidRainTypeDef]


# Detect Source or Package mode
top_package = __name__.split('.')[0]
if top_package == 'src':
    senseid_package = files('src.senseid')
else:
    senseid_package = files('senseid')
_senseid_yaml = senseid_package.joinpath('definitions').joinpath('senseid_rain.yaml').read_text()
_senseid_dict = yaml.safe_load(_senseid_yaml)
SENSEID_RAIN_DEF: SenseidRainDef = SenseidRainDef.from_dict(_senseid_dict)
