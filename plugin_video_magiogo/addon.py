# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from .http_handler import MagioGOHTTPRequestHandler
from .provider import MagioGOContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(MagioGOContentProvider, addon, http_cls=MagioGOHTTPRequestHandler)
