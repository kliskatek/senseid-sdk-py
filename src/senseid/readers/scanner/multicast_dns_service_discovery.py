import logging
from typing import Callable

from zeroconf import IPVersion, Zeroconf, ServiceBrowser, ServiceStateChange
from .. import SenseidReaderConnectionInfo, SupportedSenseidReader

logger = logging.getLogger(__name__)


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

    def start(self, reset: bool = False):
        if reset:
            self.ips = {}

        def on_service_state_change(zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange):
            if 'SpeedwayR' in name:
                info = zeroconf.get_service_info(service_type, name)
                if info is not None:
                    ipv4_addresses = info.addresses_by_version(IPVersion.V4Only)
                    if len(ipv4_addresses) > 0:
                        ipv4 = ipv4_addresses[0]
                        ip_str = str(ipv4[0]) + '.' + str(ipv4[1]) + '.' + str(ipv4[2]) + '.' + str(ipv4[3])
                        if state_change is ServiceStateChange.Added:
                            if ip_str not in self.ips:
                                logger.info('New Speedway readers found: ' + ip_str)
                                conn_infos = [
                                    SenseidReaderConnectionInfo(driver=SupportedSenseidReader.OCTANE,
                                                                connection_string=ip_str),
                                    SenseidReaderConnectionInfo(driver=SupportedSenseidReader.SPEEDWAY,
                                                                connection_string=ip_str),
                                ]
                                self.ips[ip_str] = conn_infos
                                for conn_info in conn_infos:
                                    self.notification_callback(conn_info)
                        elif state_change is ServiceStateChange.Removed:
                            if ip_str in self.ips:
                                logger.info('Speedway reader disconnected: ' + ip_str)
                                conn_infos = self.ips.pop(ip_str)
                                if self.removal_callback is not None:
                                    for conn_info in conn_infos:
                                        self.removal_callback(conn_info)

            if 'ThingMagic Mercury' in name:
                info = zeroconf.get_service_info(service_type, name)
                if info is not None:
                    ipv4_addresses = info.addresses_by_version(IPVersion.V4Only)
                    if len(ipv4_addresses) > 0:
                        ipv4 = ipv4_addresses[0]
                        ip_str = str(ipv4[0]) + '.' + str(ipv4[1]) + '.' + str(ipv4[2]) + '.' + str(ipv4[3])
                        if state_change is ServiceStateChange.Added:
                            if ip_str not in self.ips:
                                logger.info('New Mercury readers found: ' + ip_str)
                                conn_infos = [
                                    SenseidReaderConnectionInfo(driver=SupportedSenseidReader.SPEEDWAY,
                                                                connection_string=ip_str),
                                ]
                                self.ips[ip_str] = conn_infos
                                for conn_info in conn_infos:
                                    self.notification_callback(conn_info)
                        elif state_change is ServiceStateChange.Removed:
                            if ip_str in self.ips:
                                logger.info('Mercury reader disconnected: ' + ip_str)
                                conn_infos = self.ips.pop(ip_str)
                                if self.removal_callback is not None:
                                    for conn_info in conn_infos:
                                        self.removal_callback(conn_info)

        services = [
            "_http._tcp.local.",
        ]
        self.service_browser = ServiceBrowser(self.zeroconf_instance, services, handlers=[on_service_state_change])

    def stop(self):
        self.service_browser.cancel()
        self.service_browser.join()
