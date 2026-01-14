# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler
from .provider import SweetTVContentProvider

# #################################################################################################

def main(addon):
	p = ArchivCZSKContentProvider(SweetTVContentProvider, addon)
	archivCZSKHttpServer.registerRequestHandler(PlayliveTVHTTPRequestHandler(p.provider, addon, cache_life=0))
	return p
