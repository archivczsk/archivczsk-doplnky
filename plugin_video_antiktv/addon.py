# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .http_handler import AntikTVHTTPRequestHandler
from .provider import AntikTVContentProvider

# #################################################################################################

def main( addon ):
	cp = AntikTVContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id), bgservice=addon.bgservice)
	archivCZSKHttpServer.registerRequestHandler(AntikTVHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
