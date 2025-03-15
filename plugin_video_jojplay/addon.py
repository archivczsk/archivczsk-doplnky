# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .provider import JojPlayContentProvider
from .http_handler import JojPlayHTTPRequestHandler

# #################################################################################################

def main(addon):
	cp = JojPlayContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id))
	archivCZSKHttpServer.registerRequestHandler(JojPlayHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
