# -*- coding: utf-8 -*-
from Plugins.Extensions.archivCZSK.engine import client
import traceback

try:
	from .wvl3.wvdecryptcustom import WvDecrypt
except:
	client.log.error("Failed to load WV CDM - playing of DRM protected content will not be available")
	client.log.error(traceback.format_exc())

	# just dummy implementation when real one is not available
	class WvDecrypt(object):
		def __init__(self, *args, **kwargs):
			pass

		def get_content_keys(self, *args, **kwargs):
			return []
