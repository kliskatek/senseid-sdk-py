import logging
from typing import List, Callable, Optional

from impinj_llrp import ImpinjLlrp, ImpinjLlrpTagReport, ImpinjReaderMode, ImpinjSearchMode

from . import SenseidReader, SenseidReaderDetails, SenseidReaderError, SenseidReaderMode
from ..parsers import SenseidTag
from ..parsers.farsens import SenseidFarsensTag
from ..parsers.farsens.yaml import SENSEID_FARSENS_DEF
from ..parsers.legacy import SenseidLegacyTag, is_senseid_legacy_epc
from ..parsers.legacy.yaml import SENSEID_LEGACY_DEF
from ..parsers.rain import SenseidRainTag

logger = logging.getLogger(__name__)


class SenseidImpinjLlrp(SenseidReader):

    def __init__(self):
        self.driver = ImpinjLlrp()
        self.notification_callback = None
        self.error_callback = None
        self.details = None
        self._mode: SenseidReaderMode = SenseidReaderMode.SENSEID

    def connect(self, connection_string: str):
        if not self.driver.connect(ip=connection_string):
            return False
        self.driver.set_notification_callback(self._driver_notification_callback)
        self.get_details()
        return True

    @staticmethod
    def _epc_bytes(epc_hex: str) -> bytes:
        try:
            return bytes.fromhex(epc_hex)
        except (ValueError, TypeError):
            return b''

    def _build_tag(self, tag_report: ImpinjLlrpTagReport) -> SenseidTag:
        epc = tag_report.epc
        epc_bytes = self._epc_bytes(epc)

        farsens_pen = bytes(SENSEID_FARSENS_DEF.pen_header)
        if epc_bytes[:len(farsens_pen)] == farsens_pen:
            return SenseidFarsensTag(epc=epc, user_mem_hex=tag_report.user_mem)

        # SenseID Rain and SenseID Legacy share the same PEN header. They
        # are told apart by the type byte: each legacy product has its own
        # type id registered in SENSEID_LEGACY_DEF.types.
        if is_senseid_legacy_epc(epc_bytes):
            return SenseidLegacyTag(epc=epc, user_mem_hex=tag_report.user_mem)

        return SenseidRainTag(epc=epc)

    def _driver_notification_callback(self, tag_report: ImpinjLlrpTagReport):
        if self.notification_callback is not None:
            self.notification_callback(self._build_tag(tag_report))

    def disconnect(self):
        self.driver.disconnect()

    def get_details(self) -> SenseidReaderDetails:
        if self.details is None:
            info = self.driver.get_reader_info()
            if info is None:
                return None
            self.details = SenseidReaderDetails(
                model_name=info.model,
                region=info.region,
                firmware_version=info.firmware_version,
                antenna_count=info.antenna_count,
                min_tx_power=info.min_tx_power_dbm,
                max_tx_power=info.max_tx_power_dbm,
                technology=self.technology,
            )
        return self.details

    def get_tx_power(self) -> float:
        return self.driver.get_tx_power_dbm()

    def set_tx_power(self, dbm: float):
        self.driver.set_tx_power_dbm(dbm)

    def get_antenna_config(self) -> List[bool]:
        active_ports = self.driver.get_antenna_config()
        if self.details is None:
            self.get_details()
        count = self.details.antenna_count if self.details else 4
        config = [False] * count
        for port in active_ports:
            if 1 <= port <= len(config):
                config[port - 1] = True
        return config

    def set_antenna_config(self, antenna_config_array: List[bool]):
        if not (True in antenna_config_array):
            antenna_config_array[0] = True
            logger.warning('At least one antenna needs to be active. Enabling antenna 1.')
        active_ports = [idx + 1 for idx, enabled in enumerate(antenna_config_array) if enabled]
        self.driver.set_antenna_config(active_ports)

    def get_supported_modes(self) -> List[SenseidReaderMode]:
        return [SenseidReaderMode.SENSEID, SenseidReaderMode.LEGACY]

    def get_mode(self) -> SenseidReaderMode:
        return self._mode

    def set_mode(self, mode: SenseidReaderMode):
        super().set_mode(mode)
        self._mode = mode
        if mode == SenseidReaderMode.LEGACY:
            word_count = max(SENSEID_LEGACY_DEF.word_count,
                             SENSEID_FARSENS_DEF.word_count)
            reads = [{
                'memoryBank': SENSEID_LEGACY_DEF.memory_bank.value,
                'wordOffset': SENSEID_LEGACY_DEF.word_offset,
                'wordCount': word_count,
            }]
            self.driver.set_tag_memory_reads(reads)
            logger.info('Reader mode set to LEGACY (tagMemoryReads=%s)', reads)
        else:
            self.driver.set_tag_memory_reads(None)
            logger.info('Reader mode set to %s (no embedded memory reads)', mode.value)

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None],
                              error_callback: Optional[Callable[['SenseidReaderError'], None]] = None):
        self.notification_callback = notification_callback
        self.error_callback = error_callback
        return self.driver.start()

    def stop_inventory_async(self):
        return self.driver.stop()
