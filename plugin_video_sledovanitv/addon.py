# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import SledovaniTVContentProvider
from .http_handler import SledovaniTVHTTPRequestHandler

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(SledovaniTVContentProvider, addon, http_cls=SledovaniTVHTTPRequestHandler)
