# -*- coding: utf-8 -*-

from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.compat import XBMCCompatInterface

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .sledovanitv_provider import SledovaniTVContentProvider
from .http_handler import SledovaniTvHTTPRequestHandler

# #################################################################################################

__scriptid__ = 'plugin.video.sledovanitv'
__scriptname__ = 'sledovanitv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString


def sledovanitv_run(session, params):
	serialid = __addon__.getSetting('serialid')
	if not serialid or len(serialid) == 0:
		import random
		serialid = ''.join(random.choice('0123456789abcdef') for n in range(40))
		__addon__.setSetting("serialid", serialid)

	settings = {'quality':__addon__.getSetting('quality')}
	provider = SledovaniTVContentProvider(username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), pin=__addon__.getSetting('pin'), serialid=serialid, data_dir=__addon__.getAddonInfo('profile'), session=session)
	XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)


def main(addon):
	request_handler = SledovaniTvHTTPRequestHandler()

	archivCZSKHttpServer.registerRequestHandler(request_handler)
	log.info("SledovaniTV http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint(request_handler))

	return XBMCCompatInterface(sledovanitv_run)
