# -*- coding: utf-8 -*-

from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.compat import XBMCCompatInterface

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .orangetv_provider import orangetvContentProvider
from .http_handler import OrangetvHTTPRequestHandler

# #################################################################################################

__scriptid__ = 'plugin.video.orangetv'
__scriptname__ = 'orangetv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString


def orangetv_run(session, params):
	settings = {'quality':__addon__.getSetting('quality')}
	provider = orangetvContentProvider(username=__addon__.getSetting('orangetvuser'), password=__addon__.getSetting('orangetvpwd'), device_id=__addon__.getSetting('deviceid'), data_dir=__addon__.getAddonInfo('profile'), session=session)
	XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)


def main(addon):
	request_handler = OrangetvHTTPRequestHandler()
	archivCZSKHttpServer.registerRequestHandler(request_handler)
	log.info("OrangeTV http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint(request_handler))

	return XBMCCompatInterface(orangetv_run)
