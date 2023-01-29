# -*- coding: utf-8 -*-

import sys, os, uuid

from tools_xbmc.contentprovider.xbmcprovider import XBMCLoginRequiredContentProvider
from tools_xbmc.compat import XBMCCompatInterface

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from Plugins.Extensions.archivCZSK.engine.client import log
from .stalker_provider import stalkerContentProvider
from .http_handler import StalkerHTTPRequestHandler
from .stalker import StalkerCache

# #################################################################################################

__scriptid__ = 'plugin.video.stalker'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)

# #################################################################################################

def stalker_run(session, params):
	settings = {}
	provider = stalkerContentProvider(data_dir=__addon__.getAddonInfo('profile'), session=session)
	XBMCLoginRequiredContentProvider(provider, settings, __addon__, session).run(params)

# #################################################################################################

def init_all_portals():
	portals = StalkerCache.load_portals_cfg()
	data_dir = __addon__.getAddonInfo('profile')

	for portal in portals:
		StalkerCache.get(portal[1], data_dir, log.info)

# #################################################################################################

def main(addon):
	request_handler = StalkerHTTPRequestHandler()

	archivCZSKHttpServer.registerRequestHandler(request_handler)
	log.info("Stalker http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint(request_handler))
	init_all_portals()
	return XBMCCompatInterface(stalker_run)
