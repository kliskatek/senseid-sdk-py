import logging
import threading
import urllib.request
import ssl
from typing import Callable

from zeroconf import IPVersion, Zeroconf, ServiceBrowser, ServiceStateChange
from .. import SenseidReaderConnectionInfo, SupportedSenseidReader

logger = logging.getLogger(__name__)

# SSL context that skips certificate verification (R700 uses self-signed cert)
_no_verify_ctx = ssl.create_default_context()
_no_verify_ctx.check_hostname = False
_no_verify_ctx.verify_mode = ssl.CERT_NONE


def _is_iot_mode(ip: str, timeout: float = 1.5) -> bool:
    """Check if an Impinj R700 is in IoT mode by probing its REST API."""
    try:
        req = urllib.request.Request(f"https://{ip}/api/v1/system", method='GET')
        urllib.request.urlopen(req, timeout=timeout, context=_no_verify_ctx)
        return True
    except Exception:
        return False


class MulticastDnsServiceDiscoveryScanner:

    def __init__(self, notification_callback: Callable[[SenseidReaderConnectionInfo], None],
                 removal_callback: Callable[[SenseidReaderConnectionInfo], None] = None,
                 autostart: bool = False):
        self.notification_callback = notification_callback
        self.removal_callback = removal_callback
        self.service_browser: ServiceBrowser | None = None
        self.zeroconf_instance = Zeroconf(ip_version=IPVersion.V4Only)
        self.ips = {}  # ip_str -> list of SenseidReaderConnectionInfo

        if autostart:
            self.start()

    def _extract_ip(self, zeroconf, service_type, name):
        info = zeroconf.get_service_info(service_type, name)
        if info is not None:
            ipv4_addresses = info.addresses_by_version(IPVersion.V4Only)
            if len(ipv4_addresses) > 0:
                ipv4 = ipv4_addresses[0]
                return str(ipv4[0]) + '.' + str(ipv4[1]) + '.' + str(ipv4[2]) + '.' + str(ipv4[3])
        return None

    def _add_reader(self, ip_str: str, conn_infos: list):
        self.ips[ip_str] = conn_infos
        for conn_info in conn_infos:
            self.notification_callback(conn_info)

    def _remove_reader(self, ip_str: str):
        conn_infos = self.ips.pop(ip_str)
        if self.removal_callback is not None:
            for conn_info in conn_infos:
                self.removal_callback(conn_info)

    def start(self, reset: bool = False):
        if reset:
            self.ips = {}

        def on_service_state_change(zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange):
            # Impinj Speedway (R120/R220/R420) — always LLRP
            if 'SpeedwayR' in name:
                ip_str = self._extract_ip(zeroconf, service_type, name)
                if ip_str is None:
                    return
                if state_change is ServiceStateChange.Added and ip_str not in self.ips:
                    logger.info('New Speedway reader found: ' + ip_str)
                    self._add_reader(ip_str, [
                        SenseidReaderConnectionInfo(driver=SupportedSenseidReader.OCTANE, connection_string=ip_str),
                        SenseidReaderConnectionInfo(driver=SupportedSenseidReader.IMPINJ_LLRP, connection_string=ip_str),
                    ])
                elif state_change is ServiceStateChange.Removed and ip_str in self.ips:
                    logger.info('Speedway reader disconnected: ' + ip_str)
                    self._remove_reader(ip_str)

            # Impinj R700 — detect IoT vs LLRP mode
            elif name.startswith('impinj-'):
                ip_str = self._extract_ip(zeroconf, service_type, name)
                if ip_str is None:
                    return
                if state_change is ServiceStateChange.Added and ip_str not in self.ips:
                    # Probe REST API in background to avoid blocking mDNS thread
                    def _probe_and_notify(ip=ip_str):
                        if _is_iot_mode(ip):
                            driver = SupportedSenseidReader.IMPINJ_IOT
                        else:
                            driver = SupportedSenseidReader.IMPINJ_LLRP
                        logger.info(f'New Impinj R700 found: {ip} ({driver.value})')
                        if ip not in self.ips:
                            self._add_reader(ip, [
                                SenseidReaderConnectionInfo(driver=driver, connection_string=ip),
                            ])
                    threading.Thread(target=_probe_and_notify, daemon=True).start()
                elif state_change is ServiceStateChange.Removed and ip_str in self.ips:
                    logger.info('Impinj R700 reader disconnected: ' + ip_str)
                    self._remove_reader(ip_str)

            # ThingMagic Mercury — LLRP
            elif 'ThingMagic Mercury' in name:
                ip_str = self._extract_ip(zeroconf, service_type, name)
                if ip_str is None:
                    return
                if state_change is ServiceStateChange.Added and ip_str not in self.ips:
                    logger.info('New Mercury reader found: ' + ip_str)
                    self._add_reader(ip_str, [
                        SenseidReaderConnectionInfo(driver=SupportedSenseidReader.IMPINJ_LLRP, connection_string=ip_str),
                    ])
                elif state_change is ServiceStateChange.Removed and ip_str in self.ips:
                    logger.info('Mercury reader disconnected: ' + ip_str)
                    self._remove_reader(ip_str)

        services = [
            "_http._tcp.local.",
        ]
        self.service_browser = ServiceBrowser(self.zeroconf_instance, services, handlers=[on_service_state_change])

    def stop(self):
        self.service_browser.cancel()
        self.service_browser.join()
