from dataclasses import dataclass
from enum import Enum
from typing import List, Callable
from abc import ABC, abstractmethod

from dataclasses_json import dataclass_json

from src.senseid.parsers import SenseidTag


class SupportedSenseidReader(Enum):
    REDRCP = 'REDRCP'
    NURAPI = 'NURAPI'
    OCTANE = 'OCTANE'


@dataclass_json
@dataclass
class SenseidReaderConnectionInfo:
    driver: SupportedSenseidReader
    connection_string: str


@dataclass_json
@dataclass
class SenseidReaderDetails:
    model_name: str = None
    region: str = None
    firmware_version: str = None
    antenna_count: int = None
    min_tx_power: float = None
    max_tx_power: float = None


class SenseidReader(ABC):

    @abstractmethod
    def connect(self, connection_string: str):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def get_details(self) -> SenseidReaderDetails:
        pass

    @abstractmethod
    def get_tx_power(self) -> float:
        pass

    @abstractmethod
    def set_tx_power(self, dbm: float):
        pass

    @abstractmethod
    def get_antenna_config(self) -> List[bool]:
        pass

    @abstractmethod
    def set_antenna_config(self, antenna_config_array: List[bool]):
        pass

    @abstractmethod
    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None]):
        pass

    @abstractmethod
    def stop_inventory_async(self):
        pass


def get_supported_readers():
    return [reader.value for reader in SupportedSenseidReader]


def create_SenseidReader(reader_info: SenseidReaderConnectionInfo = None, notification_callback=None) -> SenseidReader:
    if reader_info.driver == SupportedSenseidReader.REDRCP:
        from .red4s import SenseidReaderRedRcp
        return SenseidReaderRedRcp(connection_string=reader_info.connection_string,
                                   notification_callback=notification_callback)
    if reader_info.driver == SupportedSenseidReader.OCTANE:
        from .octane import SenseidOctane
        return SenseidOctane()
