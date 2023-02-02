# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .provider import RebitTVContentProvider
from .http_handler import RebitTvHTTPRequestHandler

# #################################################################################################

def main(addon):
	cp = RebitTVContentProvider(addon.settings, data_dir=addon.get_info('profile'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id), bgservice=addon.bgservice)
	archivCZSKHttpServer.registerRequestHandler(RebitTvHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
