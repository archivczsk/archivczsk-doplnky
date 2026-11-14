try:
	from typing import Union, Any, Optional
except ImportError:
	pass

from ..crypto.ecc_key import ECCKey
from ..device.structs import DeviceStructs
from ..misc.exceptions import OutdatedDevice
from ..system.bcert import CertificateChain
from ..system.compat import IntEnum, decode_binary, path_string, write_file


class Device(object):
	"""Represents a PlayReady Device (.prd)"""
	CURRENT_VERSION = 3

	class SecurityLevel(IntEnum):
		SL150 = 150
		SL2000 = 2000
		SL3000 = 3000

	def __init__(self, *_, **kwargs):
		# type: (...) -> None
		group_key = kwargs.get("group_key")
		encryption_key = kwargs.get("encryption_key")
		signing_key = kwargs.get("signing_key")
		group_certificate = kwargs.get("group_certificate")
		if group_key is not None:
			group_key = decode_binary(group_key, lengths=(32, 96))
		encryption_key = decode_binary(encryption_key, lengths=(32, 96))
		if not isinstance(encryption_key, bytes):
			raise ValueError("Expecting Bytes or Base64 input, got {0!r}".format(encryption_key))

		signing_key = decode_binary(signing_key, lengths=(32, 96))
		if not isinstance(signing_key, bytes):
			raise ValueError("Expecting Bytes or Base64 input, got {0!r}".format(signing_key))

		group_certificate = decode_binary(group_certificate, prefix=b"CHAI")
		if not isinstance(group_certificate, bytes):
			raise ValueError("Expecting Bytes or Base64 input, got {0!r}".format(group_certificate))

		self.group_key = None if group_key is None else ECCKey.loads(group_key)
		self.encryption_key = ECCKey.loads(encryption_key)
		self.signing_key = ECCKey.loads(signing_key)
		self.group_certificate = CertificateChain.loads(group_certificate)
		self.security_level = self.group_certificate.get_security_level()

	@classmethod
	def loads(cls, data):
		# type: (Union[str, bytes]) -> Device
		data = decode_binary(data, prefix=b"PRD")
		if not isinstance(data, bytes):
			raise ValueError("Expecting Bytes or Base64 input, got {0!r}".format(data))

		parsed = DeviceStructs.prd.parse(data)
		return cls(**dict(parsed, group_key=parsed.get('group_key', None)))

	@classmethod
	def load(cls, path):
		# type: (Union[Path, str]) -> Device
		with open(path_string(path), "rb") as f:
			return cls.loads(f.read())

	def dumps(self, version=None):
		# type: (int) -> bytes
		if version is None:
			version = self.CURRENT_VERSION
		if self.group_key is None and version == self.CURRENT_VERSION:
			raise OutdatedDevice("Cannot dump device as version 3 without having a group key. Either provide a group key or set argument version=2")

		return DeviceStructs.prd.build(dict(
			version=version,
			group_key=self.group_key.dumps() if self.group_key else None,
			encryption_key=self.encryption_key.dumps(),
			signing_key=self.signing_key.dumps(),
			group_certificate_length=len(self.group_certificate.dumps()),
			group_certificate=self.group_certificate.dumps(),
		))

	def dump(self, path):
		# type: (Union[Path, str]) -> None
		write_file(path, self.dumps())

	def get_name(self):
		# type: () -> str
		name = "{0}_sl{1}".format(self.group_certificate.get_name(), self.group_certificate.get_security_level())
		return ''.join(char for char in name if (char.isalnum() or char in '_- ')).strip().lower().replace(" ", "_")
