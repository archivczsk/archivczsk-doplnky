# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .httphandler import PrimaPlusHTTPRequestHandler
from .provider import PrimaPlusContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(PrimaPlusContentProvider, addon, http_cls=PrimaPlusHTTPRequestHandler)
