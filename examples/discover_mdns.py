"""Discover all mDNS services on the local network. Useful to find the service name of Impinj R700 readers."""
from zeroconf import IPVersion, Zeroconf, ServiceBrowser, ServiceStateChange

def on_service_state_change(zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange):
    if state_change is not ServiceStateChange.Added:
        return
    info = zeroconf.get_service_info(service_type, name)
    if info is None:
        print(f"  [{service_type}] {name}  (no info)")
        return
    ipv4s = info.addresses_by_version(IPVersion.V4Only)
    ip_str = '.'.join(str(b) for b in ipv4s[0]) if ipv4s else '?'
    print(f"  [{service_type}] {name}  ->  {ip_str}:{info.port}")
    if info.properties:
        for k, v in info.properties.items():
            print(f"      {k} = {v}")

services = ["_http._tcp.local.", "_llrp._tcp.local."]

print(f"Browsing mDNS services: {services}")
print("Press Ctrl+C to stop.\n")

zc = Zeroconf(ip_version=IPVersion.V4Only)
browser = ServiceBrowser(zc, services, handlers=[on_service_state_change])

try:
    input()
except KeyboardInterrupt:
    pass

browser.cancel()
zc.close()
