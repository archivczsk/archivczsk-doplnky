# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .http_handler import TVNovaHTTPRequestHandler
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .provider import TVNovaContentProvider

# #################################################################################################


def main(addon):
	cp = TVNovaContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id))
	archivCZSKHttpServer.registerRequestHandler(TVNovaHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
