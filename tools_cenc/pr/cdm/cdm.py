import xml.etree.ElementTree as ET
try:
	from typing import List, Union, Optional, Dict
except ImportError:
	pass

from uuid import UUID

try:
	from Cryptodome.Cipher import AES
except ImportError:
	from Crypto.Cipher import AES

from ...wvl3.cdm.compat import Padding

from ..dep.ecpy.curves import Point, Curve

from .crypto import Crypto
from .crypto.ecc_key import ECCKey
from .license.key import Key
from .license.license import License
from .misc.exceptions import (InvalidSession, TooManySessions, InvalidXmrLicense)
#from .misc.revocation_list import RevocationList
from .misc.soap_message import SoapMessage
from .misc.storage import Storage
from .system.bcert import CertificateChain
from .system.builder import XmlBuilder
from .system.session import Session
from .system.wrmheader import WRMHeader
from .system.util import Util
from .system.compat import string_types


class Cdm(object):
	MAX_NUM_OF_SESSIONS = 16

	def __init__(
			self,
			security_level,  # type: int
			certificate_chain,  # type: Optional[CertificateChain]
			encryption_key,  # type: Optional[ECCKey]
			signing_key,  # type: Optional[ECCKey]
			client_version="10.0.16384.10011",  # type: str
	):
		# type: (...) -> None
		self.security_level = security_level
		self.certificate_chain = certificate_chain
		self.encryption_key = encryption_key
		self.signing_key = signing_key
		self.client_version = client_version

		self._wmrm_key = Point(
			x=0xc8b6af16ee941aadaa5389b4af2c10e356be42af175ef3face93254e7b0b3d9b,
			y=0x982b27b5cb2341326e56aa857dbfd5c634ce2cf9ea74fca8f2af5957efeea562,
			curve=Curve.get_curve("secp256r1")
		)

		self.__sessions = {}  # type: Dict[bytes, Session]

	@classmethod
	def from_device(cls, device):
		# type: (...) -> Cdm
		"""Initialize a Playready CDM from a Playready Device (.prd) file"""
		return cls(
			security_level=device.security_level,
			certificate_chain=device.group_certificate,
			encryption_key=device.encryption_key,
			signing_key=device.signing_key
		)

	def open(self):
		# type: () -> bytes
		"""Open a Playready Content Decryption Module (CDM) session"""
		if len(self.__sessions) > self.MAX_NUM_OF_SESSIONS:
			raise TooManySessions("Too many Sessions open ({0}).".format(self.MAX_NUM_OF_SESSIONS))

		session = Session(len(self.__sessions) + 1)
		self.__sessions[session.id] = session

		return session.id

	def close(self, session_id):
		# type: (bytes) -> None
		"""Close a Playready Content Decryption Module (CDM) session """
		session = self.__sessions.get(session_id)
		if not session:
			raise InvalidSession("Session identifier {0} is invalid.".format(Util.bytes_to_hex(session_id)))
		del self.__sessions[session_id]

	def _get_cipher_data(self, session):
		# type: (Session) -> bytes
		body = XmlBuilder.ClientData([self.certificate_chain], ["AESCBCS"])

		cipher = AES.new(
			session.xml_key.aes_key,
			AES.MODE_CBC,
			session.xml_key.aes_iv
		)

		ciphertext = cipher.encrypt(Padding.pad(
			body.encode(),
			AES.block_size
		))

		return session.xml_key.aes_iv + ciphertext

	def get_license_challenge(
			self,
			session_id,  # type: bytes
			wrm_header,  # type: Union[WRMHeader, str]
			rev_lists=None  # type: Optional[List[UUID]]
	):  # default: RevocationList.SupportedListIds
		# type: (...) -> str
		session = self.__sessions.get(session_id)
		if not session:
			raise InvalidSession("Session identifier {0} is invalid.".format(Util.bytes_to_hex(session_id)))

		if isinstance(wrm_header, string_types):
			wrm_header = WRMHeader(wrm_header)
		if not isinstance(wrm_header, WRMHeader):
			raise ValueError("Expected wrm_header to be a {0} or {1} not {2!r}".format(str, WRMHeader, wrm_header))

		if rev_lists and not isinstance(rev_lists, list):
			raise ValueError("Expected rev_lists to be a {0} not {1!r}".format(list, rev_lists))

		if wrm_header.version == WRMHeader.Version.VERSION_4_3_0_0:
			protocol_version = 5
		elif wrm_header.version == WRMHeader.Version.VERSION_4_2_0_0:
			protocol_version = 4
		else:
			protocol_version = 1

		session.signing_key = self.signing_key
		session.encryption_key = self.encryption_key

		acquire_license_message = XmlBuilder.AcquireLicenseMessage(
			wrmheader=wrm_header.dumps(),
			protocol_version=protocol_version,
			wrmserver_data=Crypto.ecc256_encrypt(self._wmrm_key, session.xml_key.get_point()),
			client_data=self._get_cipher_data(session),
			signing_key=self.signing_key,
			client_info=self.client_version,
			revocation_lists=rev_lists
		)
		soap_message = SoapMessage.create(acquire_license_message)

		return soap_message.dumps()

	def parse_license(self, session_id, soap_message):
		# type: (bytes, str) -> None
		session = self.__sessions.get(session_id)
		if not session:
			raise InvalidSession("Session identifier {0} is invalid.".format(Util.bytes_to_hex(session_id)))

		if not soap_message:
			raise InvalidXmrLicense("Cannot parse an empty licence message")
		if not isinstance(soap_message, string_types):
			raise InvalidXmrLicense("Expected licence message to be a {0}, not {1!r}".format(str, soap_message))
		if not session.encryption_key or not session.signing_key:
			raise InvalidSession("Cannot parse a license message without first making a license request")

		soap_message = SoapMessage.loads(soap_message)
		soap_message.raise_faults()

		licence = License(soap_message.get_message())
		if licence.is_verifiable():
			licence.verify()

		# if licence.rev_info is not None:
		# 	current_rev_info_file = Storage.read_file(RevocationList.CurrentRevListStorageName)

		# 	if current_rev_info_file:
		# 		new_rev_info = RevocationList.merge(ET.fromstring(current_rev_info_file), licence.rev_info)
		# 	else:
		# 		new_rev_info = licence.rev_info

		# 	new_rev_info_xml = ET.tostring(
		# 		new_rev_info,
		# 		xml_declaration=True,
		# 		encoding="utf-8"
		# 	)
		# 	Storage.write_file(RevocationList.CurrentRevListStorageName, new_rev_info_xml)
		# 	Storage.write_file(RevocationList.loads(new_rev_info).get_storage_file_name(), new_rev_info_xml)

		for xmr_license in licence.licenses:
			session.keys.append(xmr_license.get_content_key(session.encryption_key))

	def get_keys(self, session_id):
		# type: (bytes) -> List[Key]
		session = self.__sessions.get(session_id)
		if not session:
			raise InvalidSession("Session identifier {0} is invalid.".format(Util.bytes_to_hex(session_id)))

		return session.keys
