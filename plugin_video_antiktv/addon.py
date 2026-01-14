# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .http_handler import AntikTVHTTPRequestHandler
from .provider import AntikTVContentProvider

# #################################################################################################

def main( addon ):
	return ArchivCZSKContentProvider(AntikTVContentProvider, addon, http_cls=AntikTVHTTPRequestHandler)
