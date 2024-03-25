# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .httphandler import HboMaxHTTPRequestHandler
from .provider import HboMaxContentProvider

# #################################################################################################

def main(addon):
	cp = HboMaxContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id))
	archivCZSKHttpServer.registerRequestHandler(HboMaxHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
