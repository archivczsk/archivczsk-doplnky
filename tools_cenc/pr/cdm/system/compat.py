import base64
import errno
import os
import re
import sys
import xml.etree.ElementTree as ET

PY2 = sys.version_info[0] == 2

if PY2:
    from HTMLParser import HTMLParser
    from ...dep.enum34 import Enum, IntEnum

    text_type = unicode
    string_types = (str, unicode)
    html_unescape = HTMLParser().unescape
else:
    from enum import Enum, IntEnum
    from html import unescape as html_unescape

    text_type = str
    string_types = (str,)

try:
    from pathlib import Path
except ImportError:
    Path = None


def decode_binary(data, prefix=None, lengths=()):
    if isinstance(data, text_type):
        return base64.b64decode(data)
    if PY2 and isinstance(data, bytes):
        if (prefix and data.startswith(prefix)) or len(data) in lengths:
            return data
        if prefix or lengths or re.match(br"^[A-Za-z0-9+/=\s]+$", data):
            return base64.b64decode(data)
    return data


def path_string(path):
    if Path is not None and isinstance(path, Path):
        return str(path)
    if not isinstance(path, string_types):
        raise ValueError("Expecting Path object or path string, got {0!r}".format(path))
    return path


def write_file(path, data):
    path = path_string(path)
    parent = os.path.dirname(path)
    if parent:
        try:
            os.makedirs(parent)
        except OSError as error:
            if error.errno != errno.EEXIST or not os.path.isdir(parent):
                raise
    with open(path, "wb") as stream:
        stream.write(data)


def tostring(element, encoding="us-ascii"):
    if not PY2:
        return ET.tostring(element, encoding=encoding, short_empty_elements=False)
    data = ET.tostring(element, encoding=encoding)
    # ElementTree 2.7 sorts xmlns after regular attributes, changing signed XML.
    data = re.sub(
        br'(<[A-Za-z_][\w:.-]*)((?:\s+(?!xmlns=)[^\s=<>]+="[^"]*")+)(\s+xmlns="[^"]*")',
        br'\1\3\2', data
    )
    return re.sub(br"<([^\s/>]+)([^<>]*?)\s*/>", br"<\1\2></\1>", data)
