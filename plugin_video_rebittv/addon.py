# -*- coding: utf-8 -*-

from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.compat import XBMCCompatInterface

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .rebittv_provider import RebitTVContentProvider
from .http_handler import RebitTvHTTPRequestHandler

# #################################################################################################

__scriptid__ = 'plugin.video.rebittv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)

def rebit_run(session, params):
	settings = {'quality':__addon__.getSetting('quality')}
	provider = RebitTVContentProvider( username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), device_name=__addon__.getSetting('device_name'), data_dir=__addon__.getAddonInfo('profile'), session=session )
	XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)

def main(addon):
	request_handler = RebitTvHTTPRequestHandler()
	archivCZSKHttpServer.registerRequestHandler(request_handler)
	log.info("RebitTV http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint(request_handler))

	return XBMCCompatInterface(rebit_run)
