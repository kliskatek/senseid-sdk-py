"""Quick smoke test for NURAPY LEGACY mode in the SenseID SDK.

Connects to the NUR on COM6, switches to LEGACY mode (embedded user-mem
read via NUR_CMD_INVENTORYREAD 0x41), runs inventory for ~8s and prints
the parsed tags. Both Kliskatek legacy (PEN F1D3 + 0xFF marker) and
Farsens (PEN A93C) families are dispatched to their respective parsers.
"""

import logging
import time

from senseid.parsers import SenseidTag
from senseid.readers import (SenseidReaderConnectionInfo,
                                  SenseidReaderMode,
                                  SupportedSenseidReader,
                                  create_SenseidReader)

logging.basicConfig(level=logging.INFO)

connection_info = SenseidReaderConnectionInfo(
    driver=SupportedSenseidReader.NURAPY,
    connection_string='COM6',
)

reader = create_SenseidReader(connection_info)
reader.connect(connection_info.connection_string)
reader.set_mode(SenseidReaderMode.LEGACY)

seen = {}


def notification_callback(tag: SenseidTag):
    seen[tag.id] = tag
    logging.info('%s %s', tag.name, tag.id)


reader.start_inventory_async(notification_callback=notification_callback)
time.sleep(8)
reader.stop_inventory_async()
reader.set_mode(SenseidReaderMode.SENSEID)
reader.disconnect()

print('\nLEGACY mode summary:')
for tid, tag in seen.items():
    data = getattr(tag, 'data', None)
    print(f'  {tag.name:20s} id={tid}  data={data}')
