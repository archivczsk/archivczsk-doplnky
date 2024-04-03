# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .httphandler import DisneyPlusHTTPRequestHandler
from .provider import DisneyPlusContentProvider

# #################################################################################################

def main(addon):
	cp = DisneyPlusContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id))
	http_handler = DisneyPlusHTTPRequestHandler(cp, addon)
	cp.set_http_handler(http_handler)
	archivCZSKHttpServer.registerRequestHandler(http_handler)
	return ArchivCZSKContentProvider(cp, addon)
