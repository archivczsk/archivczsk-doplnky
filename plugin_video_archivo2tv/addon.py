# -*- coding: utf-8 -*-

import sys, os
from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.compat import XBMCCompatInterface

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .o2tv_provider import O2tvContentProvider
from .http_handler import O2tvHTTPRequestHandler

# #################################################################################################

__scriptid__ = 'plugin.video.archivo2tv'
__scriptname__ = 'archivo2tv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString

# #################################################################################################

def o2tv_run(session, params):
	settings = {'quality':__addon__.getSetting('quality')}

	device_id = __addon__.getSetting('deviceid')
	if not device_id or len(device_id) == 0:
		import random, string
		device_id = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(15))
		__addon__.setSetting("deviceid", device_id)

	provider = O2tvContentProvider(username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), device_id=device_id, data_dir=__addon__.getAddonInfo('profile'), session=session)

	XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)

# #################################################################################################

def main(addon):
	request_handler = O2tvHTTPRequestHandler()
	archivCZSKHttpServer.registerRequestHandler(request_handler)
	log.info("O2TV http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint(request_handler))

	return XBMCCompatInterface(o2tv_run)

# #################################################################################################
