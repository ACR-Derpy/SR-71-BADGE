"""NFC-A CRC helper."""


def crc_a(data):
    """Return the two-byte CRC_A in wire order."""
    crc = 0x6363
    for value in data:
        value ^= crc & 0xFF
        value = (value ^ (value << 4)) & 0xFF
        crc = (
            (crc >> 8)
            ^ (value << 8)
            ^ (value << 3)
            ^ (value >> 4)
        ) & 0xFFFF
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])
