# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from .httphandler import WBDMaxHTTPRequestHandler
from .provider import WBDMaxContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(WBDMaxContentProvider, addon, http_cls=WBDMaxHTTPRequestHandler)
