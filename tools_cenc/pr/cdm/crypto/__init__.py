try:
	from typing import Union, Tuple
except ImportError:
	pass

try:
	from Cryptodome.Hash import SHA256
	from Cryptodome.Signature import DSS
except ImportError:
	from Crypto.Hash import SHA256
	try:
		from Crypto.Signature import DSS
	except ImportError:
		from .ecc_fallback import DSS

SHA256Hash = type(SHA256.new())

from ...dep.ecpy.curves import Point, Curve
from ...dep.ecpy._compat import int_to_bytes

from ..crypto.elgamal import ElGamal
from ..crypto.ecc_key import ECCKey, EccKey
from ..system.util import Util


class Crypto(object):
	curve = Curve.get_curve("secp256r1")

	@staticmethod
	def ecc256_encrypt(public_key, plaintext):
		# type: (Union[ECCKey, Point], Union[Point, bytes]) -> bytes
		if isinstance(public_key, ECCKey):
			public_key = public_key.get_point(Crypto.curve)
		if not isinstance(public_key, Point):
			raise ValueError("Expecting ECCKey or Point input, got {0!r}".format(public_key))

		if isinstance(plaintext, bytes):
			plaintext = Point(
				x=Util.from_bytes(plaintext[:32], 'big'),
				y=Util.from_bytes(plaintext[32:64], 'big'),
				curve=Crypto.curve
			)
		if not isinstance(plaintext, Point):
			raise ValueError("Expecting Point or Bytes input, got {0!r}".format(plaintext))

		point1, point2 = ElGamal.encrypt(plaintext, public_key)
		return b''.join([
			int_to_bytes(point1.x, 32, 'big'),
			int_to_bytes(point1.y, 32, 'big'),
			int_to_bytes(point2.x, 32, 'big'),
			int_to_bytes(point2.y, 32, 'big')
		])

	@staticmethod
	def ecc256_decrypt(private_key, ciphertext):
		# type: (ECCKey, Union[Tuple[Point, Point], bytes]) -> bytes
		if isinstance(ciphertext, bytes):
			ciphertext = (
				Point(
					x=Util.from_bytes(ciphertext[:32], 'big'),
					y=Util.from_bytes(ciphertext[32:64], 'big'),
					curve=Crypto.curve
				),
				Point(
					x=Util.from_bytes(ciphertext[64:96], 'big'),
					y=Util.from_bytes(ciphertext[96:128], 'big'),
					curve=Crypto.curve
				)
			)
		if not isinstance(ciphertext, tuple):
			raise ValueError("Expecting Tuple[Point, Point] or Bytes input, got {0!r}".format(ciphertext))

		decrypted = ElGamal.decrypt(ciphertext, int(private_key.key.d))
		return int_to_bytes(decrypted.x, 32, 'big')

	@staticmethod
	def ecc256_sign(private_key, data):
		# type: (Union[ECCKey, EccKey], Union[SHA256Hash, bytes]) -> bytes
		if isinstance(private_key, ECCKey):
			private_key = private_key.key
		if not isinstance(private_key, EccKey):
			raise ValueError("Expecting ECCKey or EccKey input, got {0!r}".format(private_key))

		if isinstance(data, bytes):
			data = SHA256.new(data)
		if not isinstance(data, SHA256Hash) or getattr(data, "oid", None) != SHA256.new().oid:
			raise ValueError("Expecting SHA256Hash or Bytes input, got {0!r}".format(data))

		signer = DSS.new(private_key, 'fips-186-3')
		return signer.sign(data)

	@staticmethod
	def ecc256_verify(public_key, data, signature):
		# type: (Union[ECCKey, EccKey], Union[SHA256Hash, bytes], bytes) -> bool
		if isinstance(public_key, ECCKey):
			public_key = public_key.key
		if not isinstance(public_key, EccKey):
			raise ValueError("Expecting ECCKey or EccKey input, got {0!r}".format(public_key))

		if isinstance(data, bytes):
			data = SHA256.new(data)
		if not isinstance(data, SHA256Hash) or getattr(data, "oid", None) != SHA256.new().oid:
			raise ValueError("Expecting SHA256Hash or Bytes input, got {0!r}".format(data))

		verifier = DSS.new(public_key, 'fips-186-3')
		try:
			verifier.verify(data, signature)
			return True
		except ValueError:
			return False
