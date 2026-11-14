from numbers import Integral
try:
	from typing import Union
except ImportError:
	pass

try:
	from Cryptodome.Hash import SHA256
	from Cryptodome.PublicKey import ECC
	from Cryptodome.PublicKey.ECC import EccKey
except ImportError:
	from Crypto.Hash import SHA256
	try:
		from Crypto.PublicKey import ECC
		from Crypto.PublicKey.ECC import EccKey
	except ImportError:
		from . import ecc_fallback as ECC
		from .ecc_fallback import EccKey


from ...dep.ecpy.curves import Curve, Point
from ...dep.ecpy._compat import int_to_bytes

from ..system.util import Util
from ..system.compat import decode_binary, path_string, write_file


class ECCKey(object):
	"""Represents a PlayReady ECC key pair"""

	def __init__(self, key):
		# type: (EccKey) -> None
		self.key = key

	@classmethod
	def generate(cls):
		"""Generate a new ECC key pair"""
		return cls(key=ECC.generate(curve='P-256'))

	@classmethod
	def construct(cls, private_key):
		# type: (Union[bytes, int]) -> ECCKey
		"""Construct an ECC key pair from private/public bytes/ints"""
		if isinstance(private_key, bytes):
			private_key = Util.from_bytes(private_key, 'big')
		if not isinstance(private_key, Integral):
			raise ValueError("Expecting Bytes or Int input, got {0!r}".format(private_key))

		# The public key is always derived from the private key; loading the other stuff won't work
		key = ECC.construct(
			curve='P-256',
			d=private_key,
		)

		return cls(key=key)

	@classmethod
	def loads(cls, data):
		# type: (Union[str, bytes]) -> ECCKey
		data = decode_binary(data, lengths=(32, 96))
		if not isinstance(data, bytes):
			raise ValueError("Expecting Bytes or Base64 input, got {0!r}".format(data))

		if len(data) not in [96, 32]:
			raise ValueError("Invalid data length. Expecting 96 or 32 bytes, got {0}".format(len(data)))

		return cls.construct(private_key=data[:32])

	@classmethod
	def load(cls, path):
		# type: (Union[Path, str]) -> ECCKey
		with open(path_string(path), "rb") as f:
			return cls.loads(f.read())

	def dumps(self, private_only=False):
		if private_only:
			return self.private_bytes()
		return self.private_bytes() + self.public_bytes()

	def dump(self, path, private_only=False):
		# type: (Union[Path, str], bool) -> None
		write_file(path, self.dumps(private_only))

	def get_point(self, curve):
		# type: (Curve) -> Point
		return Point(self.key.pointQ.x, self.key.pointQ.y, curve)

	def private_bytes(self):
		# type: () -> bytes
		return int_to_bytes(int(self.key.d), 32, 'big')

	def private_sha256_digest(self):
		# type: () -> bytes
		hash_object = SHA256.new()
		hash_object.update(self.private_bytes())
		return hash_object.digest()

	def public_bytes(self):
		# type: () -> bytes
		return int_to_bytes(int(self.key.pointQ.x), 32, 'big') + int_to_bytes(int(self.key.pointQ.y), 32, 'big')

	def public_sha256_digest(self):
		# type: () -> bytes
		hash_object = SHA256.new()
		hash_object.update(self.public_bytes())
		return hash_object.digest()
