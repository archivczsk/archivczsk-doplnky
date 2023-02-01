# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .provider import SweetTVContentProvider
from .http_handler import SweetTvHTTPRequestHandler

# #################################################################################################

def main(addon):
	cp = SweetTVContentProvider(addon.settings, data_dir=addon.get_info('profile'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id), bgservice=addon.bgservice)
	archivCZSKHttpServer.registerRequestHandler(SweetTvHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
