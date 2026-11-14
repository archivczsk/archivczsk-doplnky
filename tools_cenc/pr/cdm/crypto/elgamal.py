
try:
	from typing import Tuple
except ImportError:
	pass

from ...dep.ecpy.curves import Curve, Point
from random import SystemRandom


class ElGamal(object):
	"""ElGamal ECC utility using ecpy"""

	curve = Curve.get_curve("secp256r1")

	@staticmethod
	def encrypt(message_point, public_key):
		"""
		Encrypt a single point with a given public key

		Returns an encrypted point pair
		"""
		ephemeral_key = SystemRandom().randrange(ElGamal.curve.order)
		point1 = ephemeral_key * ElGamal.curve.generator
		point2 = message_point + (ephemeral_key * public_key)
		return point1, point2

	@staticmethod
	def decrypt(encrypted, private_key):
		"""
		Decrypt and encrypted point pair with a given private key

		Returns a single decrypted point
		"""
		point1, point2 = encrypted
		shared_secret = private_key * point1
		decrypted_message = point2 - shared_secret
		return decrypted_message
