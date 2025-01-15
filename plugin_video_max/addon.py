# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .httphandler import WBDMaxHTTPRequestHandler
from .provider import WBDMaxContentProvider

# #################################################################################################

def main(addon):
	cp = WBDMaxContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id))
	archivCZSKHttpServer.registerRequestHandler(WBDMaxHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
