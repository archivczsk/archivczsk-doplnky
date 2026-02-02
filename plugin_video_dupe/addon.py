# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import DupeContentProvider
from .http_handler import DupeHTTPRequestHandler

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(DupeContentProvider, addon, http_cls=DupeHTTPRequestHandler)
