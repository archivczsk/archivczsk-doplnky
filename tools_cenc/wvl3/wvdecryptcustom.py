# -*- coding: utf-8 -*-

import base64
from .cdm import cdm, deviceconfig
from Plugins.Extensions.archivCZSK.engine import client
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

class DummyLogger(object):
	def debug(*args, **kwargs):
		pass

	def info(*args, **kwargs):
		pass

	def error(*args, **kwargs):
		pass

	def warning(*args, **kwargs):
		pass

class WvDecrypt(object):
	WV_SYSTEM_ID = b"\xed\xef\x8b\xa9y\xd6J\xce\xa3\xc8'\xdc\xd5\x1d!\xed"

	def __init__(self, enable_logging=False):
		if enable_logging:
			self.cdm = cdm.Cdm(client.log)
		else:
			self.cdm = cdm.Cdm(DummyLogger())

		self.device_config = deviceconfig.DeviceConfig()
		if self.device_config.load_custom_device(ArchivCZSK.get_addon('tools.cenc').get_info('data_path')):
			self.cdm.logger.info("Loaded custom CDM device informations")
		else:
			self.cdm.logger.info("Using build in CDM device informations")


	def check_pssh(self, pssh_b64):
		pssh = base64.b64decode(pssh_b64)
		if not pssh[12:28] == self.WV_SYSTEM_ID:
			new_pssh = bytearray([0, 0, 0])
			new_pssh.append(32 + len(pssh))
			new_pssh[4:] = bytearray(b'pssh')
			new_pssh[8:] = [0, 0, 0, 0]
			new_pssh[13:] = self.WV_SYSTEM_ID
			new_pssh[29:] = [0, 0, 0, 0]
			new_pssh[31] = len(pssh)
			new_pssh[32:] = pssh
			return base64.b64encode(new_pssh)
		else:
			return pssh_b64

	def get_content_keys(self, pssh, lic_cbk, service_cert_cbk=None):
		session = self.cdm.open_session(self.check_pssh(pssh), self.device_config)
		if service_cert_cbk:
			self.cdm.set_service_certificate(session, service_cert_cbk(self.cdm.CERTIFICATE_CHALLENGE))

		lic_response = lic_cbk(self.cdm.get_license_request(session))
		if not lic_response:
			self.cdm.close_session(session)
			return []

		if self.cdm.provide_license(session, lic_response) == 0:
			keys = [key.export() for key in filter(lambda k: k.type == 'CONTENT', self.cdm.get_keys(session))]
		else:
			keys = []

		self.cdm.close_session(session)
		return keys
