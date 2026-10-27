# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import SkylinkContentProvider
from .http_handler import SkylinkHTTPRequestHandler

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(SkylinkContentProvider, addon, http_cls=SkylinkHTTPRequestHandler)
