CMAC_IMPL_CRYPTODOME=1
CMAC_IMPL_CRYPTOGRAPHY=2

cmac_impl = None
try:
	from Cryptodome.Cipher import AES
	from Cryptodome.Hash import CMAC
	cmac_impl = CMAC_IMPL_CRYPTODOME
except:
	pass

if cmac_impl == None:
	try:
		from Crypto.Cipher import AES
		from Crypto.Hash import CMAC
		cmac_impl = CMAC_IMPL_CRYPTODOME
	except:
		pass

if cmac_impl == None:
	try:
		from cryptography.hazmat.primitives.cmac import CMAC
		from cryptography.hazmat.primitives.ciphers.algorithms import AES
		from cryptography.hazmat.backends.openssl.backend import backend
		cmac_impl = CMAC_IMPL_CRYPTOGRAPHY
	except:
		pass

if cmac_impl == CMAC_IMPL_CRYPTODOME:

	class CMAC_AES(object):
		def __init__(self, key):
			self.cmac_obj = CMAC.new(key, ciphermod=AES)

		def update(self, data):
			return self.cmac_obj.update(data)

		def digest(self):
			return self.cmac_obj.digest()

elif cmac_impl == CMAC_IMPL_CRYPTOGRAPHY:

	class CMAC_AES(object):
		def __init__(self, key):
			self.cmac_obj = CMAC(AES(key), backend)

		def update(self, data):
			return self.cmac_obj.update(data)

		def digest(self):
			return self.cmac_obj.finalize()
else:
	raise ImportError("No usable CMAC implementation found")


try:
	from Cryptodome.Util import Padding
except:
	try:
		from Crypto.Util import Padding
	except:
		from Crypto.Util.py3compat import bchr, bord
		# symplified version to work with CDM - only pkcs7 stype padding is supported
		class Padding:
			@staticmethod
			def pad(data_to_pad, block_size):
				padding_len = block_size-len(data_to_pad)%block_size
				padding = bchr(padding_len)*padding_len
				return data_to_pad + padding

			@staticmethod
			def unpad(padded_data, block_size):
				pdata_len = len(padded_data)
				if pdata_len % block_size:
					raise ValueError("Input data is not padded")

				padding_len = bord(padded_data[-1])
				if padding_len<1 or padding_len>min(block_size, pdata_len):
					raise ValueError("Padding is incorrect.")

				if padded_data[-padding_len:]!=bchr(padding_len)*padding_len:
					raise ValueError("PKCS#7 padding is incorrect.")
				return padded_data[:-padding_len]
