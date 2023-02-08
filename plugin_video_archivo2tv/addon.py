# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler
from .provider import O2TVContentProvider

# #################################################################################################

def main(addon):
	cp = O2TVContentProvider(addon.settings, data_dir=addon.get_info('profile'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id), bgservice=addon.bgservice)
	archivCZSKHttpServer.registerRequestHandler(PlayliveTVHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
