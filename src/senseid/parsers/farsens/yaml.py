import datetime
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Dict, List, Optional

import yaml
from dataclasses_json import dataclass_json

from ..legacy.yaml import SenseidMemoryBank
from ..rain.yaml import SenseidTransformType, SenseidValueType


@dataclass_json
@dataclass
class SenseidFarsensDataDef:
    magnitude: str
    magnitude_short: str
    unit_long: str
    unit_short: str
    type: SenseidValueType
    transform: SenseidTransformType
    coefficients: List[float]
    valid_range: Optional[List[float]] = field(default=None)


@dataclass_json
@dataclass
class SenseidFarsensTypeDef:
    name: str
    description: str
    data_def: List[SenseidFarsensDataDef]
    fw_versions: List[int]
    datasheet_url: Optional[str] = field(default=None)
    store_url: Optional[str] = field(default=None)


@dataclass_json
@dataclass
class SenseidFarsensDef:
    version: int
    date: datetime.date
    pen_header: bytearray
    memory_bank: SenseidMemoryBank
    word_offset: int
    word_count: int
    preamble: int
    data_index: int
    types: Dict[int, SenseidFarsensTypeDef]


top_package = __name__.split('.')[0]
if top_package == 'src':
    senseid_package = files('src.senseid')
else:
    senseid_package = files('senseid')
_senseid_yaml = senseid_package.joinpath('definitions').joinpath('senseid_farsens.yaml').read_text()
_senseid_dict = yaml.safe_load(_senseid_yaml)
SENSEID_FARSENS_DEF: SenseidFarsensDef = SenseidFarsensDef.from_dict(_senseid_dict)
