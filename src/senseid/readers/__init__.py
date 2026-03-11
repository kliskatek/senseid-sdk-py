from dataclasses import dataclass
from enum import Enum
from typing import List, Callable, Optional
from abc import ABC, abstractmethod

from dataclasses_json import dataclass_json

from ..parsers import SenseidTag


class SenseidReaderMode(Enum):
    DEFAULT = 'DEFAULT'
    NDEF = 'NDEF'
    BULK = 'BULK'


class SenseidReaderError(Exception):
    def __init__(self, error_type: str, message: str = ''):
        self.error_type = error_type
        self.message = message
        super().__init__(f'{error_type}: {message}')


class SupportedSenseidReader(Enum):
    REDRCP = 'REDRCP'
    NURAPI = 'NURAPI'
    NURAPY = 'NURAPY'
    OCTANE = 'OCTANE'
    IMPINJ_LLRP = 'IMPINJ_LLRP'
    KLSBLELCR = 'KLSBLELCR'
    ACR1552 = 'ACR1552'
    IMPINJ_IOT = 'IMPINJ_IOT'
    ZEBRA_LLRP = 'ZEBRA_LLRP'


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
    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None],
                              error_callback: Optional[Callable[['SenseidReaderError'], None]] = None):
        pass

    @abstractmethod
    def stop_inventory_async(self):
        pass

    def get_supported_modes(self) -> List[SenseidReaderMode]:
        return [SenseidReaderMode.DEFAULT]

    def get_mode(self) -> SenseidReaderMode:
        return SenseidReaderMode.DEFAULT

    def set_mode(self, mode: SenseidReaderMode):
        supported = self.get_supported_modes()
        if mode not in supported:
            raise ValueError(f'Mode {mode} not supported. Supported: {supported}')

    def resume_from_error(self):
        pass


def get_supported_readers():
    return [reader.value for reader in SupportedSenseidReader]


def create_SenseidReader(reader_info: SenseidReaderConnectionInfo = None, notification_callback=None) -> SenseidReader:
    if reader_info.driver == SupportedSenseidReader.REDRCP:
        from .redrcp import SenseidReaderRedRcp
        return SenseidReaderRedRcp()
    if reader_info.driver == SupportedSenseidReader.OCTANE:
        from .octane import SenseidOctane
        return SenseidOctane()
    if reader_info.driver == SupportedSenseidReader.NURAPI:
        from .nurapi import SenseidNurapi
        return SenseidNurapi()
    if reader_info.driver == SupportedSenseidReader.NURAPY:
        from .nurapy import SenseidNurapy
        return SenseidNurapy()
    if reader_info.driver == SupportedSenseidReader.IMPINJ_LLRP:
        from .speedway import SenseidSpeedway
        return SenseidSpeedway()
    if reader_info.driver == SupportedSenseidReader.KLSBLELCR:
        from .klsblelcr import SenseidKlSbleLcr
        return SenseidKlSbleLcr()
    if reader_info.driver == SupportedSenseidReader.ACR1552:
        from .acr1552 import SenseidAcr1552
        return SenseidAcr1552()
    if reader_info.driver == SupportedSenseidReader.IMPINJ_IOT:
        from .impinj_iot import SenseidImpinjIot
        return SenseidImpinjIot()
    if reader_info.driver == SupportedSenseidReader.ZEBRA_LLRP:
        from .zebra_llrp import SenseidZebraLlrp
        return SenseidZebraLlrp()
