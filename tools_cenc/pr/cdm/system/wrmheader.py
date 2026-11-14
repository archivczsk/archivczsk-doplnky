import base64
import hashlib
try:
	from typing import List, Optional, Union
except ImportError:
	pass
from uuid import UUID
import xml.etree.ElementTree as ET

try:
    from Cryptodome.Cipher import AES
except:
    from Crypto.Cipher import AES

from ..misc.exceptions import InvalidWrmHeader, InvalidChecksum
from ..system.util import Util
from .compat import Enum, PY2, decode_binary, text_type


class WRMHeader(object):
    """Represents a PlayReady WRM Header"""

    class SignedKeyID(object):
        class AlgId(Enum):
            AESCTR = "AESCTR"
            AESCBC = "AESCBC"
            COCKTAIL = "COCKTAIL"
            UNKNOWN = "UNKNOWN"

            @classmethod
            def _missing_(cls, value):
                return cls.UNKNOWN

        def __init__(self, value, alg_id, checksum):
            self.value = value
            self.alg_id = alg_id
            self.checksum = checksum

        @classmethod
        def load(cls, value, alg_id, checksum):
            return cls(
                value=UUID(bytes_le=base64.b64decode(value)),
                alg_id=cls.AlgId(alg_id),
                checksum=base64.b64decode(checksum) if checksum else None
            )

        def __repr__(self):
            return 'SignedKeyID(value="{0}", alg_id={1}, checksum={2})'.format(self.value, self.alg_id, self.checksum)

        def verify(self, content_key):
            if self.value is None:
                raise InvalidChecksum("Key ID must not be empty")
            if self.checksum is None:
                raise InvalidChecksum("Checksum must not be empty")

            if self.alg_id == self.AlgId.AESCTR:
                cipher = AES.new(content_key, mode=AES.MODE_ECB)
                encrypted = cipher.encrypt(self.value.bytes_le)
                checksum = encrypted[:8]
            elif self.alg_id == self.AlgId.COCKTAIL:
                buffer = content_key.ljust(21, b"\x00")
                for _ in range(5):
                    buffer = hashlib.sha1(buffer).digest()
                checksum = buffer[:7]
            else:
                raise InvalidChecksum("Algorithm ID must be either \"AESCTR\" or \"COCKTAIL\"")

            return checksum == self.checksum

    class Version(Enum):
        VERSION_4_0_0_0 = "4.0.0.0"
        VERSION_4_1_0_0 = "4.1.0.0"
        VERSION_4_2_0_0 = "4.2.0.0"
        VERSION_4_3_0_0 = "4.3.0.0"
        UNKNOWN = "UNKNOWN"

        @classmethod
        def _missing_(cls, value):
            return cls.UNKNOWN

    def __init__(self, data):
        if not data:
            raise InvalidWrmHeader("Data must not be empty")

        if isinstance(data, text_type):
            if data.lstrip().startswith("<"):
                data = data.encode("utf-16-le")
            else:
                data = base64.b64decode(data)
        elif PY2 and isinstance(data, bytes):
            data = decode_binary(data)

        if isinstance(data, bytes) and data.lstrip().startswith(b"<") and b"\x00" not in data[:4]:
            data = data.decode("utf-8").encode("utf-16-le")

        self._raw_data = data
        self._root = ET.fromstring(data)
        Util.remove_namespaces(self._root)

        if self._root.tag != "WRMHEADER":
            raise InvalidWrmHeader("Data is not a valid WRMHEADER")

        self.version = self.Version(self._root.attrib.get("version"))

        self.key_ids = []
        self.la_url = None
        self.lui_url = None
        self.ds_id = None
        self.custom_attributes = None
        self.decryptor_setup = None

        if self.version == self.Version.VERSION_4_0_0_0:
            self._load_v4_0_data(self._root)
        elif self.version == self.Version.VERSION_4_1_0_0:
            self._load_v4_1_data(self._root)
        elif self.version == self.Version.VERSION_4_2_0_0:
            self._load_v4_2_data(self._root)
        elif self.version == self.Version.VERSION_4_3_0_0:
            self._load_v4_3_data(self._root)

    def __repr__(self):
        attrs = ", \n          ".join("{0}={1!r}".format(k, v) for k, v in self.__dict__.items())
        return "{0}({1})".format(self.__class__.__name__, attrs)

    @staticmethod
    def _attr(element, name):
        return element.attrib.get(name) if element is not None else None

    def _load_v4_0_data(self, parent):
        Data = parent.find("DATA")

        Kid = Data.findtext("KID")
        AlgId = Data.findtext("PROTECTINFO/ALGID")
        Checksum = Data.findtext("CHECKSUM")

        self.key_ids = [self.SignedKeyID.load(Kid, AlgId, Checksum)]

        self.la_url = Data.findtext("LA_URL")
        self.lui_url = Data.findtext("LUI_URL")
        self.ds_id = Data.findtext("DS_ID")

        self.custom_attributes = Data.find("CUSTOMATTRIBUTES")

    def _load_v4_1_data(self, parent):
        Data = parent.find("DATA")

        Kid = Data.find("PROTECTINFO/KID")
        if Kid is not None:
            Value = Kid.get("VALUE")
            AlgId = Kid.get("ALGID")
            Checksum = Kid.get("CHECKSUM")

            self.key_ids.append(self.SignedKeyID.load(Value, AlgId, Checksum))

        self.la_url = Data.findtext("LA_URL")
        self.lui_url = Data.findtext("LUI_URL")
        self.ds_id = Data.findtext("DS_ID")

        self.custom_attributes = Data.find("CUSTOMATTRIBUTES")
        self.decryptor_setup = Data.findtext("DECRYPTORSETUP")

    def _load_v4_2_data(self, parent):
        Data = parent.find("DATA")

        for kid in Data.findall("PROTECTINFO/KIDS/KID"):
            Value = kid.get("VALUE")
            AlgId = kid.get("ALGID")
            Checksum = kid.get("CHECKSUM")

            self.key_ids.append(self.SignedKeyID.load(Value, AlgId, Checksum))

        self.la_url = Data.findtext("LA_URL")
        self.lui_url = Data.findtext("LUI_URL")
        self.ds_id = Data.findtext("DS_ID")

        self.custom_attributes = Data.find("CUSTOMATTRIBUTES")
        self.decryptor_setup = Data.findtext("DECRYPTORSETUP")

    def _load_v4_3_data(self, parent):
        Data = parent.find("DATA")

        for kid in Data.findall("PROTECTINFO/KIDS/KID"):
            Value = kid.get("VALUE")
            AlgId = kid.get("ALGID")
            Checksum = kid.get("CHECKSUM")

            self.key_ids.append(self.SignedKeyID.load(Value, AlgId, Checksum))

        self.la_url = Data.findtext("LA_URL")
        self.lui_url = Data.findtext("LUI_URL")
        self.ds_id = Data.findtext("DS_ID")

        self.custom_attributes = Data.find("CUSTOMATTRIBUTES")
        self.decryptor_setup = Data.findtext("DECRYPTORSETUP")

    def dumps(self):
        return self._raw_data.decode("utf-16-le")
