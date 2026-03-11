import logging
import select
import socket
import struct
import threading
import uuid
import re
from typing import Callable, List, Set

from .. import SenseidReaderConnectionInfo, SupportedSenseidReader

logger = logging.getLogger(__name__)

WS_DISCOVERY_MULTICAST = '239.255.255.250'
WS_DISCOVERY_PORT = 3702

PROBE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
               xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery">
  <soap:Header>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
    <wsa:MessageID>urn:uuid:{message_id}</wsa:MessageID>
  </soap:Header>
  <soap:Body>
    <wsd:Probe/>
  </soap:Body>
</soap:Envelope>"""


class WsDiscoveryScanner:

    def __init__(self, notification_callback: Callable[[SenseidReaderConnectionInfo], None],
                 removal_callback: Callable[[SenseidReaderConnectionInfo], None] = None,
                 autostart: bool = False):
        self.notification_callback = notification_callback
        self.removal_callback = removal_callback
        self._running = False
        self._thread: threading.Thread | None = None
        self._known_ips: Set[str] = set()
        self._scan_interval = 10.0
        self._probe_timeout = 3.0

        if autostart:
            self.start()

    def start(self, reset: bool = False):
        if reset:
            self._known_ips = set()
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, daemon=True, name='ws-discovery-scanner')
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _scan_loop(self):
        while self._running:
            try:
                self._probe()
            except Exception as e:
                logger.debug(f'WS-Discovery probe error: {e}')
            # Sleep in small increments so we can stop quickly
            for _ in range(int(self._scan_interval * 10)):
                if not self._running:
                    break
                threading.Event().wait(0.1)

    @staticmethod
    def _get_local_ips() -> List[str]:
        """Get all local IPv4 addresses."""
        ips = []
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if ip not in ips and not ip.startswith('127.'):
                    ips.append(ip)
        except Exception:
            pass
        if not ips:
            ips = ['0.0.0.0']
        return ips

    def _probe(self):
        message_id = str(uuid.uuid4())
        probe = PROBE_TEMPLATE.format(message_id=message_id).encode('utf-8')

        local_ips = self._get_local_ips()
        sockets = []

        for local_ip in local_ips:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                socket.inet_aton(local_ip))
                sock.setblocking(False)
                sock.sendto(probe, (WS_DISCOVERY_MULTICAST, WS_DISCOVERY_PORT))
                sockets.append(sock)
                logger.debug(f'WS-Discovery probe sent via {local_ip}')
            except Exception as e:
                logger.debug(f'WS-Discovery: could not send via {local_ip}: {e}')

        if not sockets:
            return

        # Collect responses from all sockets
        deadline = threading.Event()
        deadline.wait(self._probe_timeout)

        for sock in sockets:
            while True:
                try:
                    data, addr = sock.recvfrom(65535)
                    ip = addr[0]
                    response = data.decode('utf-8', errors='ignore')
                    self._parse_response(response, ip)
                except (BlockingIOError, OSError):
                    break

        for sock in sockets:
            sock.close()

    def _parse_response(self, response: str, ip: str):
        # ISO 24791-3 RDMP is the RFID Reader Management Profile
        rdmp_patterns = ['ISO24791-3', 'iso/24791', 'rdmpdev',
                         'FX9600', 'FX7500', 'zebra', 'Zebra', 'ZEBRA']
        is_rfid_reader = any(pattern in response for pattern in rdmp_patterns)

        if is_rfid_reader and ip not in self._known_ips:
            logger.info(f'New Zebra reader found via WS-Discovery: {ip}')
            self._known_ips.add(ip)
            conn_info = SenseidReaderConnectionInfo(
                driver=SupportedSenseidReader.ZEBRA_LLRP,
                connection_string=ip,
            )
            self.notification_callback(conn_info)
