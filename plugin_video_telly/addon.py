# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler
from .provider import TellyContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(TellyContentProvider, addon, http_cls=PlayliveTVHTTPRequestHandler)
