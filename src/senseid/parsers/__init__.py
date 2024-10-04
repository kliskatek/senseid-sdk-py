from dataclasses import dataclass
from enum import Enum
from typing import List

from dataclasses_json import dataclass_json


class SenseidTechnologies(Enum):
    RAIN = 'RAIN'
    BLE = 'BLE'
    NFC = 'NFC'


@dataclass_json
@dataclass
class SenseidData:
    magnitude: str
    unit_long: str
    unit_short: str
    value: float


@dataclass_json
@dataclass
class SenseidTag:
    technology: SenseidTechnologies
    id: str
    name: str
    description: str
    data: List[SenseidData] | None
