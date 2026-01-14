# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .http_handler import TVNovaHTTPRequestHandler
from .provider import TVNovaContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(TVNovaContentProvider, addon, http_cls=TVNovaHTTPRequestHandler)
