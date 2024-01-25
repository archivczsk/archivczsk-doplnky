# -*- coding: utf-8 -*-

import sys, os, uuid

from tools_xbmc.contentprovider.xbmcprovider import XBMCLoginRequiredContentProvider
from tools_xbmc.compat import XBMCCompatInterface

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from Plugins.Extensions.archivCZSK.engine.client import log
from .stalker_provider import stalkerContentProvider
from .http_handler import StalkerHTTPRequestHandler
from .stalker import StalkerCache

# #################################################################################################

def stalker_run(session, params, addon):
	settings = {}
	provider = stalkerContentProvider(data_dir=addon.getAddonInfo('data_path'), session=session, addon=addon)
	XBMCLoginRequiredContentProvider(provider, settings, addon, session).run(params)

# #################################################################################################

def init_all_portals(addon):
	portals = StalkerCache.load_portals_cfg()
	data_dir = addon.get_info('data_path')

	for portal in portals:
		StalkerCache.get(portal[1], data_dir, log.info)

# #################################################################################################

def main(addon):
	request_handler = StalkerHTTPRequestHandler(addon)

	archivCZSKHttpServer.registerRequestHandler(request_handler)
	log.info("Stalker http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint(request_handler))
	init_all_portals(addon)
	return XBMCCompatInterface(stalker_run, addon)
