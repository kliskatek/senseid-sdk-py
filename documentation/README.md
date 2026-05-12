# senseid

[![PyPI - Version](https://img.shields.io/pypi/v/senseid.svg)](https://pypi.org/project/senseid)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/senseid.svg)](https://pypi.org/project/senseid)

Python SDK for SenseID smart sensor tags. Parse sensor data from RAIN RFID, BLE, and NFC tags, and control supported reader devices through a unified interface.

## Features

- **Multi-technology parsing**: Decode SenseID sensor data from RAIN (UHF RFID), BLE beacons, and NFC tags
- **Legacy + Farsens RAIN families**: Read tags whose sensor data lives in User memory (Kliskatek legacy, Farsens RM family) through a single LEGACY reader mode
- **Unified reader interface**: Control different RFID/NFC readers through a single API
- **Auto-discovery**: Scan for supported readers via serial port, mDNS, and PC/SC
- **YAML-driven definitions**: Tag types and sensor calibration defined in YAML files

## Supported Readers

| Reader | Driver | Interface |
|--------|--------|-----------|
| Impinj R700 | `IMPINJ_IOT` | REST API (IoT Device Interface) |
| Impinj Speedway R420/R220/R120 | `IMPINJ_LLRP` | LLRP |
| Zebra FX9600 | `ZEBRA_LLRP` | LLRP |
| NordicID Sampoo / Stix | `NURAPY` | NUR API |
| Phychips RED4S | `REDRCP` | RedRCP (serial) |
| ACS ACR1552 | `ACR1552` | PC/SC (NFC) |
| Kliskatek BLE Reader | `KLSBLELCR` | BLE |

## Installation

```console
pip install senseid
```

## Quick Start

### Parse a RAIN RFID tag

```python
from senseid.parsers.rain import SenseidRainTag

tag = SenseidRainTag('000000F1D301010000012301')
print(tag.name)          # Tag model name
print(tag.sn)            # Serial number
for d in tag.data:
    print(f"{d.magnitude}: {d.value} {d.unit_short}")
```

### Scan for readers and run inventory

```python
from senseid.parsers import SenseidTag
from senseid.readers import SupportedSenseidReader, create_SenseidReader
from senseid.readers.scanner import SenseidReaderScanner

scanner = SenseidReaderScanner(autostart=True)
connection_info = scanner.wait_for_reader_of_type(SupportedSenseidReader.IMPINJ_IOT, timeout_s=10)
scanner.stop()

if connection_info is None:
    print('No reader found')
    exit()

reader = create_SenseidReader(connection_info)
reader.connect(connection_info.connection_string)

def on_tag(tag: SenseidTag):
    print(f"{tag.name} | SN: {tag.sn} | {tag.data}")

reader.start_inventory_async(notification_callback=on_tag)
input("Press Enter to stop...")
reader.stop_inventory_async()
reader.disconnect()
```

## Reader modes

`SenseidReader.set_mode(SenseidReaderMode.X)` switches between sensor data
sources. The set of supported modes depends on the reader; query it with
`get_supported_modes()`.

| Mode | Supported on | What it does |
|------|--------------|--------------|
| `SENSEID` | RAIN readers | Inventory only. Sensor data is decoded from the EPC (standard SenseID family). |
| `LEGACY` | Impinj R700 (today) | Inventory + embedded Read on User memory (USER@`0x100`, 6 words). Adds support for Kliskatek legacy and Farsens tags whose sensor payload lives outside the EPC. Standard SenseID tags keep working in this mode too. |
| `NDEF` / `BULK` | ACR1552 (NFC) | NDEF read vs. block-bulk read of the tag. |

In `LEGACY` mode the wrapper dispatches each inventory event to the right
parser based on the EPC:

- EPC starts with `00 00 00 F1 D3` and byte 6 ∈ `0x01..0xFE` → `SenseidRainTag` (standard SenseID).
- EPC starts with `00 00 00 F1 D3` and byte 6 == `0xFF` → `SenseidLegacyTag` (Kliskatek legacy, EVAL-LEGACY-* line).
- EPC starts with `00 00 00 A9 3C` → `SenseidFarsensTag` (Farsens RM family: Fenix-RM, Hygro-Fenix-RM, Kineo-RM, Magneto-RM, Cyclon-RM, …).
- Anything else → `SenseidRainTag` as a generic "Rain ID".

The same dispatch is performed in `SENSEID` mode; the only difference is
that without an embedded Read the legacy / Farsens parsers leave
`tag.data = None` (the tag is still reported with its correct name and SN).

## API Reference

### Parsers

#### `SenseidRainTag(epc: str | bytearray)`

Parses a standard SenseID RAIN EPC. Rejects legacy-family EPCs
(byte 6 == `0xFF`) so they fall through to `SenseidLegacyTag`.

#### `SenseidLegacyTag(epc, user_mem_hex=None)`

Parses a Kliskatek legacy tag. The EPC follows the SenseID layout but byte
6 is fixed to `0xFF` (family marker). The actual sensor payload comes from
the User-memory blob (`user_mem_hex`); when omitted, the parser still
populates `id`, `name`, `sn`, etc., and leaves `data = None`.

#### `SenseidFarsensTag(epc, user_mem_hex=None)`

Parses a Farsens RM tag. The EPC has a distinct PEN (`00 00 00 A9 3C`) and
a 5-byte big-endian `productId` that selects the model. The User-memory
datagram begins with preamble `0xAA` and a `fw_version` byte; channels
are mostly `float32` little-endian.

#### `SenseidBleTag(beacon)`

Parses a BLE advertisement payload into a `SenseidTag`.

#### `parse_nfc_ndef(ndef_data, uid) -> (SenseidTag, type_id)`

Parses NFC NDEF data into a `SenseidTag`.

### `SenseidTag`

| Field | Type | Description |
|-------|------|-------------|
| `technology` | `SenseidTechnologies` | `RAIN`, `BLE`, or `NFC` |
| `id` | `str` | Tag identifier (EPC hex, BLE MAC, NFC UID) |
| `name` | `str` | Tag model name |
| `description` | `str` | Tag description |
| `sn` | `int` | Serial number |
| `fw_version` | `int` | Firmware version |
| `data` | `list[SenseidData]` | Parsed sensor measurements (may be `None`) |
| `timestamp` | `datetime` | Read timestamp |

### `SenseidData`

| Field | Type | Description |
|-------|------|-------------|
| `magnitude` | `str` | Measurement name (e.g. "Temperature") |
| `magnitude_short` | `str` | Short name (e.g. "T") |
| `unit_long` | `str` | Unit name (e.g. "Celsius") |
| `unit_short` | `str` | Unit symbol (e.g. "C") |
| `value` | `float` | Calibrated value |

### Readers

#### `SenseidReaderScanner`

| Method | Description |
|--------|-------------|
| `start()` | Start scanning for readers (serial, mDNS, PC/SC) |
| `stop()` | Stop scanning |
| `get_readers()` | Get list of discovered readers |
| `wait_for_reader_of_type(type, timeout_s)` | Block until a reader of the given type is found |

#### `SenseidReader`

| Method | Description |
|--------|-------------|
| `connect(connection_string)` | Connect to reader |
| `disconnect()` | Disconnect |
| `get_details()` | Returns model, region, firmware, antenna count, power limits, and `technology` (RAIN/BLE/NFC) |
| `get_tx_power()` / `set_tx_power(dbm)` | Get/set TX power in dBm |
| `get_antenna_config()` / `set_antenna_config(list[bool])` | Get/set active antennas |
| `get_supported_modes()` / `get_mode()` / `set_mode(mode)` | Query / change the operating mode (`SENSEID`, `LEGACY`, …) |
| `start_inventory_async(callback)` | Start inventory with tag notification callback |
| `stop_inventory_async()` | Stop inventory |

## Tag definitions

Tag families, models, and calibration coefficients are defined as YAML in
the [`senseid-sdk-definitions`](https://github.com/kliskatek/senseid-sdk-definitions)
repository (included here as a Git submodule under `src/senseid/definitions/`).
See its [README](https://github.com/kliskatek/senseid-sdk-definitions/blob/main/README.md)
for the schema and the meaning of the family-marker byte.

## License

`senseid` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
