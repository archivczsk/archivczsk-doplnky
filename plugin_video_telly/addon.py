# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import TellyContentProvider
from .httphandler import TellyHTTPRequestHandler

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(TellyContentProvider, addon, http_cls=TellyHTTPRequestHandler)
