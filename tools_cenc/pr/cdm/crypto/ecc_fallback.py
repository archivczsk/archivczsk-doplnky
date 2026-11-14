import hashlib
from random import SystemRandom

from ...dep.ecpy._compat import int_from_bytes, int_to_bytes
from ...dep.ecpy.curves import Curve, Point
from ...dep.ecpy.ecdsa import ECDSA
from ...dep.ecpy.keys import ECPrivateKey, ECPublicKey


_curve = Curve.get_curve("secp256r1")


class EccKey(object):
	def __init__(self, point, d=None):
		self.pointQ = point
		self.d = d


def construct(curve, d=None, point_x=None, point_y=None):
	if curve != "P-256":
		raise ValueError("Unsupported curve: {0}".format(curve))
	if d is not None:
		if not 1 <= d < _curve.order:
			raise ValueError("Invalid private key")
		return EccKey(d * _curve.generator, d)
	if point_x is None or point_y is None or not (0 <= point_x < _curve.field and 0 <= point_y < _curve.field):
		raise ValueError("Invalid public key")
	point = Point(point_x, point_y, _curve, check=False)
	if not _curve.is_on_curve(point):
		raise ValueError("Invalid public key")
	return EccKey(point)


def generate(curve):
	return construct(curve, d=SystemRandom().randrange(1, _curve.order))


class DSS(object):
	@staticmethod
	def new(key, mode):
		if mode != "fips-186-3":
			raise ValueError("Unsupported signature mode: {0}".format(mode))
		return _Signer(key)


class _Signer(object):
	def __init__(self, key):
		self.key = key
		self.ecdsa = ECDSA(fmt="ITUPLE")

	def sign(self, data):
		if self.key.d is None:
			raise TypeError("Private key required for signing")
		signature = self.ecdsa.sign_rfc6979(
			data.digest(), ECPrivateKey(self.key.d, _curve), hashlib.sha256
		)
		if signature is None:
			raise ValueError("Failed to generate ECDSA signature")
		return int_to_bytes(signature[0], 32, 'big') + int_to_bytes(signature[1], 32, 'big')

	def verify(self, data, signature):
		if len(signature) != 64:
			raise ValueError("Invalid signature length")
		values = (int_from_bytes(signature[:32], 'big'), int_from_bytes(signature[32:], 'big'))
		if not self.ecdsa.verify(data.digest(), values, ECPublicKey(self.key.pointQ)):
			raise ValueError("Invalid signature")
