import datetime
from dataclasses import dataclass, field
from enum import Enum
from importlib.resources import files
from typing import Dict, List, Optional

import yaml
from dataclasses_json import dataclass_json

from ..rain.yaml import SenseidTransformType, SenseidValueType


class SenseidMemoryBank(Enum):
    USER = 'user'
    TID = 'tid'
    RESERVED = 'reserved'


@dataclass_json
@dataclass
class SenseidLegacyDataDef:
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
class SenseidLegacyTypeDef:
    name: str
    description: str
    data_def: List[SenseidLegacyDataDef]
    fw_versions: List[int]
    datasheet_url: Optional[str] = field(default=None)
    store_url: Optional[str] = field(default=None)


@dataclass_json
@dataclass
class SenseidLegacySkipWhen:
    fw_version: List[int] = field(default_factory=list)


@dataclass_json
@dataclass
class SenseidLegacyDef:
    version: int
    date: datetime.date
    pen_header: bytearray
    epc_family_marker: int
    memory_bank: SenseidMemoryBank
    word_offset: int
    word_count: int
    types: Dict[int, SenseidLegacyTypeDef]
    skip_when: SenseidLegacySkipWhen = field(default_factory=SenseidLegacySkipWhen)


top_package = __name__.split('.')[0]
if top_package == 'src':
    senseid_package = files('src.senseid')
else:
    senseid_package = files('senseid')
_senseid_yaml = senseid_package.joinpath('definitions').joinpath('senseid_legacy.yaml').read_text()
_senseid_dict = yaml.safe_load(_senseid_yaml)
SENSEID_LEGACY_DEF: SenseidLegacyDef = SenseidLegacyDef.from_dict(_senseid_dict)
