# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .http_handler import O2HTTPRequestHandler
from .provider import O2TVContentProvider

# #################################################################################################

def main(addon):
	cp = O2TVContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id), bgservice=addon.bgservice)
	archivCZSKHttpServer.registerRequestHandler(O2HTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
