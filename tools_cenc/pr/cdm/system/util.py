import xml.etree.ElementTree as ET

from ...dep.ecpy._compat import int_to_bytes


class Util(object):

    @staticmethod
    def remove_namespaces(element):
        # type: (ET.Element) -> None
        for elem in element.iter():
            elem.tag = elem.tag.split('}')[-1]

    @staticmethod
    def un_pad(name):
        # type: (bytes) -> str
        return name.rstrip(b'\x00').decode("utf-8", errors="ignore")

    @staticmethod
    def to_bytes(n):
        # type: (int) -> bytes
        byte_len = (n.bit_length() + 7) // 8
        if byte_len % 2 != 0:
            byte_len += 1
        return int_to_bytes(n, byte_len, 'big')

    @staticmethod
    def from_bytes(data, byteorder):
        # type: (bytes, str) -> int
        """Convert bytes to int (Python 2.7 compatible)"""
        if byteorder == 'big':
            result = 0
            for byte in data:
                result = (result << 8) | (byte if isinstance(byte, int) else ord(byte))
            return result
        elif byteorder == 'little':
            result = 0
            for i, byte in enumerate(data):
                result |= (byte if isinstance(byte, int) else ord(byte)) << (8 * i)
            return result
        else:
            raise ValueError("byteorder must be 'big' or 'little'")

    @staticmethod
    def bytes_to_hex(data):
        # type: (bytes) -> str
        """Convert bytes to hex string (Python 2.7 compatible)"""
        return ''.join('{:02x}'.format(byte if isinstance(byte, int) else ord(byte)) for byte in data)
