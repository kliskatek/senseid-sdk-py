from dataclasses import dataclass
from enum import Enum
from typing import List
from abc import ABC, abstractmethod

from dataclasses_json import dataclass_json


class SupportedSenseidReader(Enum):
    RED4S = 'RED4S'
    NUR = 'NUR'
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
    def connect(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def get_details(self):
        pass

    @abstractmethod
    def get_tx_power(self):
        pass

    @abstractmethod
    def set_tx_power(self, dbm):
        pass

    @abstractmethod
    def get_antenna_config(self):
        pass

    @abstractmethod
    def set_antenna_config(self, antenna_config_array: List[bool]):
        pass

    @abstractmethod
    def start_inventory_async(self):
        pass

    @abstractmethod
    def stop_inventory_async(self):
        pass


def get_supported_readers():
    return [reader.value for reader in SupportedSenseidReader]


def create_SenseidReader(reader_info: SenseidReaderConnectionInfo = None, notification_callback=None) -> SenseidReader:
    if reader_info.driver == SupportedSenseidReader.RED4S:
        from .red4s import SenseidReaderRedRcp
        return SenseidReaderRedRcp(connection_string=reader_info.connection_string,
                                   notification_callback=notification_callback)
    if reader_info.driver == SupportedSenseidReader.OCTANE:
        from .octane import SenseidOctane
        return SenseidOctane(connection_string=reader_info.connection_string,
                             notification_callback=notification_callback)
