# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .http_handler import MagioGOHTTPRequestHandler
from .provider import MagioGOContentProvider

# #################################################################################################

def main(addon):
	cp = MagioGOContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id), bgservice=addon.bgservice)
	archivCZSKHttpServer.registerRequestHandler(MagioGOHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
