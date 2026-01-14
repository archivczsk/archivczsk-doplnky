# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import JojPlayContentProvider
from .http_handler import JojPlayHTTPRequestHandler

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(JojPlayContentProvider, addon, http_cls=JojPlayHTTPRequestHandler)
