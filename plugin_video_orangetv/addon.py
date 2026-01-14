# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import OrangeTVContentProvider
from .http_handler import OrangeTVHTTPRequestHandler

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(OrangeTVContentProvider, addon, http_cls=OrangeTVHTTPRequestHandler)
