# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .http_handler import DokumentyTVHTTPRequestHandler
from .provider import DokumentyTvContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(DokumentyTvContentProvider, addon, http_cls=DokumentyTVHTTPRequestHandler)
