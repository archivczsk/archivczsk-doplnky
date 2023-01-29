# -*- coding: utf-8 -*-

from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.compat import XBMCCompatInterface

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .telly_provider import tellyContentProvider
from .http_handler import TellyHTTPRequestHandler

# #################################################################################################

__scriptid__ = 'plugin.video.telly'
__scriptname__ = 'telly'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)

def telly_run(session, params):
	provider = tellyContentProvider(data_dir=__addon__.getAddonInfo('profile'), session=session)
	settings = {'quality':__addon__.getSetting('quality')}
	XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)


def main(addon):
	request_handler = TellyHTTPRequestHandler()

	archivCZSKHttpServer.registerRequestHandler(request_handler)
	log.info("Telly http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint(request_handler))

	return XBMCCompatInterface(telly_run)
