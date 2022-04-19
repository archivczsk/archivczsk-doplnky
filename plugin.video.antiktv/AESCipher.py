# -*- coding: utf-8 -*-

from Crypto.Cipher import AES
import Crypto.Random
import binascii
import sys

BS = AES.block_size
pad = lambda x: x + (BS - len(x) % BS) * chr(BS - len(x) % BS).encode("ascii")

if sys.version_info[0] == 2:
	unpad = lambda s : s[0:-ord(s[-1])]
else:
	unpad = lambda s : s[0:-s[-1]]

class AESCipher:
	def __init__( self, key ):
		"""
		Requires hex encoded param as a key
		"""
		self.key = binascii.a2b_hex(key)

	def encrypt( self, raw ):
		"""
		Returns hex encoded encrypted value!
		"""
		raw = pad(raw)
		iv = Crypto.Random.new().read(AES.block_size);
		cipher = AES.new( self.key, AES.MODE_CBC, iv )
#		return binascii.b2a_hex( iv + cipher.encrypt( raw ) )
		return iv + cipher.encrypt( raw )

	def decrypt( self, enc, iv=None ):
		"""
		Requires hex encoded param to decrypt
		"""
		if iv == None:
			iv = enc[:16]
			enc= enc[16:]

		cipher = AES.new(self.key, AES.MODE_CBC, iv )
		return unpad(cipher.decrypt( enc))
