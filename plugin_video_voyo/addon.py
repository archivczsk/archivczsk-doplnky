# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler
from .provider import VoyoContentProvider

# #################################################################################################

def main(addon):
	cp = VoyoContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id))
	archivCZSKHttpServer.registerRequestHandler(DashHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
