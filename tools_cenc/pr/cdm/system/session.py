from typing import Optional

try:
	from Cryptodome.Random import get_random_bytes
except:
	from Crypto.Random import get_random_bytes

from ..license.key import Key
from ..crypto.ecc_key import ECCKey
from ..license.xml_key import XmlKey


class Session:
	def __init__(self, number: int):
		self.number = number
		self.id = get_random_bytes(16)
		self.xml_key = XmlKey()
		self.signing_key: Optional[ECCKey] = None
		self.encryption_key: Optional[ECCKey] = None
		self.keys: list[Key] = []
