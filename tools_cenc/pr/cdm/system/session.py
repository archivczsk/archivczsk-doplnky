
try:
	from typing import Optional, List
except ImportError:
	pass

try:
	from Cryptodome.Random import get_random_bytes
except:
	from Crypto.Random import get_random_bytes

from ..license.key import Key
from ..crypto.ecc_key import ECCKey
from ..license.xml_key import XmlKey


class Session(object):
	def __init__(self, number):
		# type: (int) -> None
		self.number = number
		self.id = get_random_bytes(16)
		self.xml_key = XmlKey()
		self.signing_key = None  # type: Optional[ECCKey]
		self.encryption_key = None  # type: Optional[ECCKey]
		self.keys = []  # type: List[Key]
