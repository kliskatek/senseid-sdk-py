from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from dataclasses_json import dataclass_json


class SenseidTechnologies(Enum):
    RAIN = 'RAIN'
    BLE = 'BLE'
    NFC = 'NFC'


@dataclass_json
@dataclass
class SenseidData:
    magnitude: str
    magnitude_short: str
    unit_long: str
    unit_short: str
    value: float


@dataclass_json
@dataclass
class SenseidTag:
    technology: SenseidTechnologies
    fw_version: int
    sn: int
    id: str
    name: str
    description: str
    data: List[SenseidData] | None
    timestamp: datetime = field(default_factory=datetime.now)
    datasheet_url: Optional[str] = field(default=None)
    store_url: Optional[str] = field(default=None)
