# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .http_handler import VoyoHTTPRequestHandler
from .provider import VoyoContentProvider

# #################################################################################################

def main(addon):
	cp = VoyoContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id))
	archivCZSKHttpServer.registerRequestHandler(VoyoHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
