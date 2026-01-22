# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from .provider import TvNoeContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(TvNoeContentProvider, addon, http_cls=HlsHTTPRequestHandler)
