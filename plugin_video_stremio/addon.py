# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import StremioContentProvider
from .http_handler import StremioHTTPRequestHandler

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(StremioContentProvider, addon, http_cls=StremioHTTPRequestHandler)
