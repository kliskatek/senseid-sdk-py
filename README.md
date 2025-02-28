# senseid

[![PyPI - Version](https://img.shields.io/pypi/v/senseid.svg)](https://pypi.org/project/senseid)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/senseid.svg)](https://pypi.org/project/senseid)

-----

## Table of Contents

- [Installation](#installation)
- [Parsers](#parsers)
- [Readers](#readers)
- [License](#license)

## Installation

```console
pip install senseid
```

## Parsers

The senseid.parsers package provides the means to automatically parse the information of any SID tag either from the EPC for RFID tags or from the BLE beacon data for BLE tags.

### Usage with RFID SID tags
Create SenseidRainTag object from EPC HEX string or from EPC bytearray:
```python
# Parse from EPC string
tag = SenseidRainTag('000000F1D301010000012301')

# Parse from EPC bytearray
tag = SenseidRainTag(bytearray([0x00, 0x00, 0x00, 0xF1, 0xD3, 0x01, 0x01, 0x00, 0x00, 0x01, 0x23, 0x01]))
```
The returning object will contain all the parsed information of the RFID SID tag. This object can be used as is or converted to a dict or a JSON if needed.
```python
# Print content of parsed tag object
logging.info(tag)

# Convert to dict
tag_dict = tag.to_dict()
logging.info(tag_dict)

# Convert to json
tag_json = tag.to_json(indent=2)
logging.info(tag_json)
```

## Readers
The senseid.readers package provides a generic reader interface to scan SID tags regardless the used reader device. It handles the configuration of the different devices to properly work with the SID tags. The package also provides a scanner for automatic reader discovery of supported devices.

### Suported devices
The following readers are supported. Some of them can be controlled with more than one driver.
* Impinj Speedway ([octane-sdk-wrapper](https://github.com/kliskatek/driver-rain-py-octane)/[sllurp](https://github.com/sllurp/sllurp))
  + R420
  + R220
  + R120
* NordicID NUR ([nurapi](https://github.com/kliskatek/driver-rain-py-nurapi)/[nurapy](https://github.com/kliskatek/driver-rain-py-nurapy))
  + Sampoo
  + Stix
* Phychips RED ([redrcp](https://github.com/kliskatek/driver-rain-py-redrcp))
  * RED4S evaluation board

### Usage of scanner
The scanner can work asynchronously with a notification callback or can be used in blocking mode to get the desired type of reader.

First create a scanner instance and start it. Define notification callback if needed.
```python
def scanner_notification_callback(new_reader: SenseidReaderConnectionInfo):
    logging.info(new_reader)

# Scan readers with notifications
scanner = SenseidReaderScanner(notification_callback=scanner_notification_callback, autostart=True)
```

Get list of already discovered readers whenever.
```python
# Get all readers found by the scanner
reader_list = scanner.get_readers()
logging.info(reader_list)
```

For blocking usage, wait until the a reader of the desired type is found.
```python
# Or wait until desired reader is found
nur_reader = scanner.wait_for_reader_of_type(reader_type=SupportedSenseidReader.NURAPI, timeout_s=1)
logging.info(nur_reader)
scanner.stop()
```

Finally, stop the scanner.
```python
scanner.stop()
```
### Usage of readers
First get the connection info of the reader.

This can be done either using the scanner:

```python
scanner = SenseidReaderScanner(autostart=True)
connection_info = scanner.wait_for_reader_of_type(SupportedSenseidReader.OCTANE, timeout_s=5)

if connection_info is None:
    print('No reader found')
    exit()
```
or manually:

```python
connection_info = SenseidReaderConnectionInfo(driver=SupportedSenseidReader.OCTANE, connection_string='192.168.0.10')
```
Then connect to the reader:
```python
er = create_SenseidReader(connection_info)
sid_reader.connect(connection_info.connection_string)
```
The antenna configuration and TX power can be configured as desired:
```python
logging.info('Setting antenna configurations')
sid_reader.set_antenna_config(antenna_config_array=[True, False])
sid_reader.get_antenna_config()

logging.info('Setting max TX power')
sid_reader.set_tx_power(sid_reader.get_details().max_tx_power)
sid_reader.get_tx_power()
```

Define a notification callback for read tags and start inventory:
```python
def notification_callback(epc: SenseidTag):
    logging.info(epc)


logging.info('Starting inventory')
sid_reader.start_inventory_async(notification_callback=notification_callback)
```

Finally stop the inventory and disconnect the reader
```python
logging.info('Stopping inventory')
sid_reader.stop_inventory_async()

logging.info('Disconnecting from reader')
sid_reader.disconnect()
```
## License

`senseid` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
