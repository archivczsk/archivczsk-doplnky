# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .http_handler import DokumentyTVHTTPRequestHandler
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .provider import DokumentyTvContentProvider

# #################################################################################################

def main(addon):
	cp = DokumentyTvContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id))
	archivCZSKHttpServer.registerRequestHandler(DokumentyTVHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
