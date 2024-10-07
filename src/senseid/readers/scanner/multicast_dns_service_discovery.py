import logging
from typing import Callable

from zeroconf import IPVersion, Zeroconf, ServiceBrowser, ServiceStateChange
from .. import SenseidReaderConnectionInfo, SupportedSenseidReader

logger = logging.getLogger(__name__)


class MulticastDnsServiceDiscoveryScanner:

    def __init__(self, notification_callback: Callable[[SenseidReaderConnectionInfo], None], autostart: bool = False):
        self.notification_callback = notification_callback
        self.service_browser: ServiceBrowser | None = None
        self.zeroconf_instance = Zeroconf(ip_version=IPVersion.V4Only)
        self.ips = []

        if autostart:
            self.start()

    def start(self, reset: bool = False):
        if reset:
            self.ips = []

        def on_service_state_change(zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange):
            if 'SpeedwayR' in name:
                if state_change is ServiceStateChange.Added:
                    info = zeroconf.get_service_info(service_type, name)
                    if info is not None:
                        ipv4_addresses = info.addresses_by_version(IPVersion.V4Only)
                        if len(ipv4_addresses) > 0:
                            ipv4 = ipv4_addresses[0]
                            if ipv4 not in self.ips:
                                ip_str = str(ipv4[0]) + '.' + str(ipv4[1]) + '.' + str(ipv4[2]) + '.' + str(ipv4[3])
                                logger.info('New Speedway readers found: ' + ip_str)
                                self.ips.append(ip_str)
                                self.notification_callback(
                                    SenseidReaderConnectionInfo(driver=SupportedSenseidReader.OCTANE,
                                                                connection_string=ip_str))

        services = [
            "_http._tcp.local.",
        ]
        self.service_browser = ServiceBrowser(self.zeroconf_instance, services, handlers=[on_service_state_change])

    def stop(self):
        self.service_browser.cancel()
        self.service_browser.join()
