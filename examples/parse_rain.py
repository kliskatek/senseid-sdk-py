import logging

from src.senseid.parsers.rain import SenseidRainTag

logging.basicConfig(level=logging.DEBUG)

# Parse from EPC string
tag = SenseidRainTag('000000F1D301010000012301')
logging.info(tag)

# Parse from EPC bytearray
tag = SenseidRainTag(bytearray([0x00, 0x00, 0x00, 0xF1, 0xD3, 0x01, 0x01, 0x00, 0x00, 0x01, 0x23, 0x01]))
logging.info(tag)

# Convert to dict
tag_dict = tag.to_dict()
logging.info(tag_dict)

# Convert to json
tag_json = tag.to_json(indent=2)
logging.info(tag_json)