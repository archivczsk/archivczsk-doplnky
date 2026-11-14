from cryptography.hazmat.primitives.keywrap import aes_key_unwrap
from ....wvl3.cdm.compat import CMAC_AES

def derive_wrapping_key():
	"""
	NIST SP 800-108 (Rev. 1)
	"Recommendation for Key Derivation Using Pseudorandom Functions"

	https://doi.org/10.6028/NIST.SP.800-108r1
	"""

	KeyDerivationCertificatePrivateKeysWrap = bytes(bytearray([
		0x9c, 0xe9, 0x34, 0x32, 0xc7, 0xd7, 0x40, 0x16,
		0xba, 0x68, 0x47, 0x63, 0xf8, 0x01, 0xe1, 0x36
	]))

	CTK_TEST = bytes(bytearray([
		0x8B, 0x22, 0x2F, 0xFD, 0x1E, 0x76, 0x19, 0x56,
		0x59, 0xCF, 0x27, 0x03, 0x89, 0x8C, 0x42, 0x7F
	]))

	cmac = CMAC_AES(CTK_TEST)

	cmac.update(b"\x01" + KeyDerivationCertificatePrivateKeysWrap + b"\x00" * 17 + b"\x00\x80")

	derived_wrapping_key = cmac.digest()

	return derived_wrapping_key

def unwrap_wrapped_key(wrapped_key):
	"""
	IETF RFC 3394
	"Advanced Encryption Standard (AES) Key Wrap Algorithm"

	https://www.rfc-editor.org/rfc/rfc3394
	"""

	wrapping_key = derive_wrapping_key()
	unwrapped_key = aes_key_unwrap(wrapping_key, wrapped_key)

	# bytes 0 -32: unwrapped key
	# bytes 32-48: random bytes

	return unwrapped_key[:32]