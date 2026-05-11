# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from .provider import TvheadendContentProvider
from .http_handler import TvheadendHTTPRequestHandler

def main(addon):
	return ArchivCZSKContentProvider(TvheadendContentProvider, addon, http_cls=TvheadendHTTPRequestHandler)
