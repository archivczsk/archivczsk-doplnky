# -*- coding: utf-8 -*-
from Plugins.Extensions.archivCZSK.engine import client
import traceback

try:
	from .pr.prdecryptcustom import PrDecrypt
except:
	client.log.error("Failed to load PR CDM - playing of DRM protected content will not be available")
	client.log.error(traceback.format_exc())

	# just dummy implementation when real one is not available
	class PrDecrypt(object):
		__instance = None

		@staticmethod
		def get_instance():
			if PrDecrypt.__instance == None:
				PrDecrypt.__instance = PrDecrypt()

			return PrDecrypt.__instance

		def __init__(self, *args, **kwargs):
			pass

		def get_content_keys(self, *args, **kwargs):
			return []
