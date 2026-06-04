import base64
import json
import logging
import ssl
import urllib.error
import urllib.request
from typing import List, Callable, Optional

from impinj_iot import ImpinjIot, ImpinjIotTagReport, RfMode, DEFAULT_USER, DEFAULT_PASS

from . import SenseidReader, SenseidReaderDetails, SenseidReaderError, SenseidReaderMode
from ..parsers import SenseidTag
from ..parsers.farsens import SenseidFarsensTag
from ..parsers.farsens.yaml import SENSEID_FARSENS_DEF
from ..parsers.senseread import SenseidSenseReadTag, is_senseid_senseread_epc
from ..parsers.senseread.yaml import SENSEID_SENSEREAD_DEF
from ..parsers.rain import SenseidRainTag

logger = logging.getLogger(__name__)

_NO_VERIFY_CTX = ssl.create_default_context()
_NO_VERIFY_CTX.check_hostname = False
_NO_VERIFY_CTX.verify_mode = ssl.CERT_NONE


def _find_schema_node(obj, key):
    """Depth-first search for the first dict found under `key` anywhere in a
    (possibly deeply nested) JSON-schema structure. Used to pull device
    limits out of the inventory preset schema."""
    if isinstance(obj, dict):
        node = obj.get(key)
        if isinstance(node, dict):
            return node
        for value in obj.values():
            found = _find_schema_node(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_schema_node(value, key)
            if found is not None:
                return found
    return None


class SenseidImpinjIot(SenseidReader):

    @staticmethod
    def probe_auth(connection_string: str, timeout: float = 2.0) -> dict:
        """Probe the R700 IoT REST API to learn whether it requires HTTP
        authentication, without connecting. Issues an unauthenticated
        GET /api/v1/system:
          - 200 -> {'auth_required': False, 'auth_scheme': 'none'}
          - 401 -> reads the WWW-Authenticate header to report 'basic'/'digest'
          - unreachable (LLRP mode, offline) -> 'unreachable'
        """
        req = urllib.request.Request(f"https://{connection_string}/api/v1/system", method='GET')
        try:
            urllib.request.urlopen(req, timeout=timeout, context=_NO_VERIFY_CTX)
            return {'auth_required': False, 'auth_scheme': 'none'}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                challenge = (e.headers.get('WWW-Authenticate', '') or '').strip().lower()
                scheme = 'digest' if challenge.startswith('digest') else 'basic'
                return {'auth_required': True, 'auth_scheme': scheme}
            # Any other HTTP status means the REST API answered without
            # demanding auth (e.g. 403/404) -> treat as no auth required.
            return {'auth_required': False, 'auth_scheme': 'none'}
        except Exception:
            return {'auth_required': False, 'auth_scheme': 'unreachable'}

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        self.driver = ImpinjIot()
        self.notification_callback = None
        self.error_callback = None
        self.details = None
        self._mode: SenseidReaderMode = SenseidReaderMode.SENSEID
        self._username = username or DEFAULT_USER
        self._password = password or DEFAULT_PASS
        self._ip: Optional[str] = None

    def _api_get(self, path: str, timeout: float = 4.0) -> Optional[dict]:
        """Authenticated GET against the reader's REST API, returning parsed
        JSON or None on any failure. Used for fields the low-level driver
        doesn't expose."""
        if not self._ip:
            return None
        req = urllib.request.Request(f"https://{self._ip}{path}", method='GET')
        token = base64.b64encode(f"{self._username}:{self._password}".encode()).decode()
        req.add_header('Authorization', f'Basic {token}')
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_NO_VERIFY_CTX) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return None

    def connect(self, connection_string: str):
        self._ip = connection_string
        if not self.driver.connect(ip=connection_string, user=self._username, password=self._password):
            return False
        self.driver.set_notification_callback(self._driver_notification_callback)
        self.get_details()
        # Set MAX TX Power
        self.driver.set_tx_power(self.details.max_tx_power)
        # Enable first antenna
        antenna_config = [False] * self.details.antenna_count
        antenna_config[0] = True
        self.driver.set_antenna_config(antenna_config)
        # Set SenseID compatible RF mode (static 246 = M4, BLF 320kHz, Tari 15.6us,
        # DR 64/3). LLRP DENSE_READER_M4 would map similar in ETSI but tag-side
        # behaviour can differ slightly; pin the static mode for determinism.
        self.driver.set_rf_mode(RfMode.STATIC_246)
        return True

    def _driver_notification_callback(self, tag_report: ImpinjIotTagReport):
        if self.notification_callback is None:
            return
        self.notification_callback(self._build_tag(tag_report))

    def _build_tag(self, tag_report: ImpinjIotTagReport) -> SenseidTag:
        # Identify the tag family from the EPC so both SENSEID and SENSEREAD
        # modes name the tag correctly. user_mem is only populated in
        # SENSEREAD mode; in SENSEID mode the senseRead/Farsens parsers still
        # recognise the model from the EPC and just leave data=None.
        epc_hex = tag_report.epc
        try:
            epc_bytes = bytes.fromhex(epc_hex)
        except (ValueError, TypeError):
            return SenseidRainTag(epc=epc_hex)

        farsens_pen = bytes(SENSEID_FARSENS_DEF.pen_header)
        if epc_bytes[:len(farsens_pen)] == farsens_pen:
            return SenseidFarsensTag(epc=epc_hex, user_mem_hex=tag_report.user_mem)

        if is_senseid_senseread_epc(epc_bytes):
            return SenseidSenseReadTag(epc=epc_hex, user_mem_hex=tag_report.user_mem)

        return SenseidRainTag(epc=epc_hex)

    def disconnect(self):
        self.driver.disconnect()

    def get_details(self) -> SenseidReaderDetails:
        if self.details is None:
            info = self.driver.get_reader_info()
            if info is None:
                return None
            # The driver reads firmware from /api/v1/system, which on Octane
            # 10.3 has no firmware field, so it falls back to the REST API
            # spec version (1.x). The real Octane firmware lives in
            # /api/v1/system/image -> primaryFirmware ("10.3.0+git...build").
            firmware = info.firmware_version
            image = self._api_get('/api/v1/system/image')
            if image and image.get('primaryFirmware'):
                firmware = image['primaryFirmware'].split('+')[0]

            # /api/v1/caps is gone on Octane 10.3, so the driver returns
            # hardcoded antenna-count/power fallbacks. The authoritative
            # limits live in the inventory preset schema: antennaPort.maximum
            # is the antenna count and transmitPowerCdbm min/max are the power
            # bounds (in cdBm).
            antenna_count = info.antenna_count
            min_cdbm = info.min_tx_power_cdbm
            max_cdbm = info.max_tx_power_cdbm
            schema = self._api_get('/api/v1/profiles/inventory/presets-schema')
            if schema:
                ap = _find_schema_node(schema, 'antennaPort')
                tp = _find_schema_node(schema, 'transmitPowerCdbm')
                if ap and isinstance(ap.get('maximum'), int):
                    antenna_count = ap['maximum']
                if tp:
                    if isinstance(tp.get('minimum'), int):
                        min_cdbm = tp['minimum']
                    if isinstance(tp.get('maximum'), int):
                        max_cdbm = tp['maximum']

            self.details = SenseidReaderDetails(
                model_name=info.model,
                region=info.region,
                firmware_version=firmware,
                antenna_count=antenna_count,
                min_tx_power=min_cdbm / 100.0,
                max_tx_power=max_cdbm / 100.0,
                technology=self.technology,
                serial_number=info.serial_number,
            )
        return self.details

    def get_tx_power(self) -> float:
        return self.driver.get_tx_power()

    def set_tx_power(self, dbm: float):
        if self.details is None:
            self.get_details()
        if dbm > self.details.max_tx_power:
            dbm = self.details.max_tx_power
            logger.warning('Power set to max power: ' + str(dbm))
        if dbm < self.details.min_tx_power:
            dbm = self.details.min_tx_power
            logger.warning('Power set to min power: ' + str(dbm))
        self.driver.set_tx_power(dbm=dbm)

    def get_antenna_config(self) -> List[bool]:
        return self.driver.get_antenna_config()

    def set_antenna_config(self, antenna_config_array: List[bool]):
        if not (True in antenna_config_array):
            antenna_config_array[0] = True
            logger.warning('At least one antenna needs to be active. Enabling antenna 1.')
        self.driver.set_antenna_config(antenna_config_array)

    def get_supported_modes(self) -> List[SenseidReaderMode]:
        return [SenseidReaderMode.SENSEID, SenseidReaderMode.SENSEREAD]

    def get_mode(self) -> SenseidReaderMode:
        return self._mode

    def set_mode(self, mode: SenseidReaderMode):
        super().set_mode(mode)
        self._mode = mode
        if mode == SenseidReaderMode.SENSEREAD:
            # word_count comes from the senseRead yaml. Sized for the largest
            # datagram in the family (currently 8 bytes for 3-axis sensors);
            # smaller datagrams (RHAT, AT, CTN) read the same window and the
            # parser ignores the trailing bytes.
            word_count = SENSEID_SENSEREAD_DEF.word_count
            reads = [{
                'memoryBank': SENSEID_SENSEREAD_DEF.memory_bank.value,
                'wordOffset': SENSEID_SENSEREAD_DEF.word_offset,
                'wordCount': word_count,
            }]
            self.driver.set_tag_memory_reads(reads)
            # Restrict inventory to the SenseID family (the PEN's first byte is
            # 0x00) so competing non-SenseID tags (e.g. commercial 0xE2... tags)
            # don't share the carrier. Without this the R700 hops between tags,
            # the senseRead tag loses power between rounds and its Rocky100 SPI
            # datagram (USER 0x100) is almost never refreshed when read
            # (data≈0). With the carrier held on the SenseID tags the read hits
            # ~98%. An 8-bit Select on the first EPC byte (offset 32 = after the
            # 16-bit CRC + 16-bit PC) is enough to drop the commercial tags.
            pen = SENSEID_SENSEREAD_DEF.pen_header
            tag_filter = {'selectFilters': [{
                'mask': {'memoryBank': 'epc', 'offset': 32,
                         'maskHex': f'{pen[0]:02X}', 'length': 8},
                'matchingAction': 'include',
                'notMatchingAction': 'exclude',
            }]}
            self.driver.set_tag_filter(tag_filter)
            logger.info('Reader mode set to SENSEREAD (tagMemoryReads=%s, filter=%s)', reads, tag_filter)
        else:
            self.driver.set_tag_memory_reads(None)
            self.driver.set_tag_filter(None)
            logger.info('Reader mode set to %s (no embedded memory reads)', mode.value)

    def start_inventory_async(self, notification_callback: Callable[[SenseidTag], None],
                              error_callback: Optional[Callable[['SenseidReaderError'], None]] = None):
        self.notification_callback = notification_callback
        self.error_callback = error_callback
        return self.driver.start()

    def stop_inventory_async(self):
        return self.driver.stop()
