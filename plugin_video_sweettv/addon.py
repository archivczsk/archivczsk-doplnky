# -*- coding: utf-8 -*-

from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.compat import XBMCCompatInterface

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from sweettv_provider import SweetTVContentProvider
from .http_handler import SweetTvHTTPRequestHandler

# #################################################################################################

__scriptid__ = 'plugin.video.sweettv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)


def sweettv_run(session, params):
	settings = {'quality':__addon__.getSetting('quality')}

	device_id = __addon__.getSetting('device_id')

	if device_id == '':
		device_id = str(uuid.uuid4())
		__addon__.setSetting('device_id', device_id)

	provider = SweetTVContentProvider(username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), device_id=device_id, data_dir=__addon__.getAddonInfo('profile'), session=session)
	XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)


def main(addon):
	request_handler = SweetTvHTTPRequestHandler()
	archivCZSKHttpServer.registerRequestHandler(request_handler)
	log.info("SweetTV http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint(request_handler))

	return XBMCCompatInterface(sweettv_run)
