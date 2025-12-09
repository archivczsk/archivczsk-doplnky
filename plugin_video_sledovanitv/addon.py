# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .provider import SledovaniTVContentProvider
from .http_handler import SledovaniTVHTTPRequestHandler

# #################################################################################################

def main(addon):
	cp = SledovaniTVContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id), http_endpoint_rel=archivCZSKHttpServer.getAddonEndpoint(addon.id, relative=True), bgservice=addon.bgservice)
	archivCZSKHttpServer.registerRequestHandler(SledovaniTVHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
