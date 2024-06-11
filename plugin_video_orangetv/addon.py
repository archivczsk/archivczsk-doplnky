# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .provider import OrangeTVContentProvider
from .http_handler import OrangeTVHTTPRequestHandler

# #################################################################################################

def main(addon):
	cp = OrangeTVContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id), http_endpoint_rel=archivCZSKHttpServer.getAddonEndpoint(addon.id, relative=True), bgservice=addon.bgservice)
	archivCZSKHttpServer.registerRequestHandler(OrangeTVHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
