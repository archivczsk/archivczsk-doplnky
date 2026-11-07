# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import CanalplusContentProvider
from .http_handler import CanalplusHTTPRequestHandler

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(CanalplusContentProvider, addon, http_cls=CanalplusHTTPRequestHandler)
