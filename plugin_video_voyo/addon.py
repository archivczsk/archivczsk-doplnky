# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from .http_handler import VoyoHTTPRequestHandler
from .provider import VoyoContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(VoyoContentProvider, addon, http_cls=VoyoHTTPRequestHandler)
