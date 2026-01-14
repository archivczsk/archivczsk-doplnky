# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from .http_handler import OneplayHTTPRequestHandler
from .provider import OneplayTVContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(OneplayTVContentProvider, addon, http_cls=OneplayHTTPRequestHandler)
