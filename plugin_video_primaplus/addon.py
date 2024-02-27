# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .httphandler import PrimaPlusHTTPRequestHandler
from .provider import PrimaPlusContentProvider

# #################################################################################################

def main(addon):
	cp = PrimaPlusContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id))
	archivCZSKHttpServer.registerRequestHandler(PrimaPlusHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
