import binascii
import operator


def int_from_bytes(data, byteorder):
    if byteorder not in ("big", "little"):
        raise ValueError("byteorder must be 'big' or 'little'")
    data = bytes(bytearray(data))
    if byteorder == "little":
        data = data[::-1]
    return int(binascii.hexlify(data) or b"0", 16)


def int_to_bytes(value, length, byteorder):
    value = operator.index(value)
    length = operator.index(length)
    if byteorder not in ("big", "little"):
        raise ValueError("byteorder must be 'big' or 'little'")
    if length < 0:
        raise ValueError("length argument must be non-negative")
    if value < 0 or value.bit_length() > length * 8:
        raise OverflowError("int too big to convert")
    if not length:
        return b""
    data = binascii.unhexlify(format(value, "0{}x".format(length * 2)))
    return data if byteorder == "big" else data[::-1]
