# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from .httphandler import DisneyPlusHTTPRequestHandler
from .provider import DisneyPlusContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(DisneyPlusContentProvider, addon, http_cls=DisneyPlusHTTPRequestHandler)
