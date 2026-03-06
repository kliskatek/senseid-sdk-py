# senseid

[![PyPI - Version](https://img.shields.io/pypi/v/senseid.svg)](https://pypi.org/project/senseid)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/senseid.svg)](https://pypi.org/project/senseid)

Python SDK for SenseID smart sensor tags. Parse sensor data from RAIN RFID, BLE, and NFC tags, and control supported reader devices through a unified interface.

## Features

- **Multi-technology parsing**: Decode SenseID sensor data from RAIN (UHF RFID), BLE beacons, and NFC tags
- **Unified reader interface**: Control different RFID/NFC readers through a single API
- **Auto-discovery**: Scan for supported readers via serial port, mDNS, and PC/SC
- **YAML-driven definitions**: Tag types and sensor calibration defined in YAML files
- **Sensor data extraction**: Temperature, humidity, and other magnitudes with automatic calibration

## Supported Readers

| Reader | Driver | Interface |
|--------|--------|-----------|
| Impinj R700 | `IMPINJ_IOT` | REST API (IoT Device Interface) |
| Impinj Speedway R420/R220/R120 | `OCTANE` / `SPEEDWAY` | Octane SDK / LLRP |
| NordicID Sampoo / Stix | `NURAPI` / `NURAPY` | NUR API |
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

## API Reference

### Parsers

#### `SenseidRainTag(epc: str | bytearray)`

Parses a RAIN RFID EPC into a `SenseidTag` with decoded sensor data. Accepts hex string or bytearray.

#### `SenseidBleTag(beacon: str | bytearray)`

Parses a BLE advertisement payload into a `SenseidTag`.

#### `parse_nfc_ndef(ndef_data: bytearray, uid: str) -> (SenseidTag, type_id)`

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
| `data` | `list[SenseidData]` | Parsed sensor measurements |
| `timestamp` | `datetime` | Read timestamp |

### `SenseidData`

| Field | Type | Description |
|-------|------|-------------|
| `magnitude` | `str` | Measurement name (e.g. "Temperature") |
| `magnitude_short` | `str` | Short name (e.g. "Temp") |
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
| `get_details()` | Get model, region, firmware, antenna count, power limits |
| `get_tx_power()` / `set_tx_power(dbm)` | Get/set TX power in dBm |
| `get_antenna_config()` / `set_antenna_config(list[bool])` | Get/set active antennas |
| `start_inventory_async(callback)` | Start inventory with tag notification callback |
| `stop_inventory_async()` | Stop inventory |

## License

`senseid` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
