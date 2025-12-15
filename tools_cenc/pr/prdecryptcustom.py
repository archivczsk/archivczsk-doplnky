# -*- coding: utf-8 -*-

import os

from .cdm.cdm import Cdm
from .cdm.device import Device
from .cdm.system.pssh import PSSH

from Plugins.Extensions.archivCZSK.engine import client
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

PR_DEVICE = os.path.join(ArchivCZSK.get_addon('tools.cenc').get_info('data_path'), 'device.prd')

class DummyLogger(object):
	def debug(*args, **kwargs):
		pass

	def info(*args, **kwargs):
		pass

	def error(*args, **kwargs):
		pass

	def warning(*args, **kwargs):
		pass

class PrDecrypt(object):
	def __init__(self, enable_logging=False):
		if os.path.isfile(PR_DEVICE):
			client.log.info("[PR] Loaded custom CDM device")
			device = Device.load(PR_DEVICE)
		else:
			client.log.info("[PR] Using build in CDM device")
			device = Device.loads('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')

		self.cdm = Cdm.from_device(device)


	def get_content_keys(self, pssh, lic_cbk):
		pssh = PSSH(pssh)
		session = self.cdm.open()
#		self.cdm.get_license_challenge(session, pssh.wrm_headers[0], rev_lists=RevocationList.SupportedListIds)
		request = self.cdm.get_license_challenge(session, pssh.wrm_headers[0])

		lic_response = lic_cbk(request)

		if not lic_response:
			self.cdm.close(session)
			return []

		self.cdm.parse_license(session, lic_response.decode('utf-8'))

		keys = ["{}:{}".format(key.key_id.hex, key.key.hex())  for key in self.cdm.get_keys(session) ]
		self.cdm.close(session)

		return keys
