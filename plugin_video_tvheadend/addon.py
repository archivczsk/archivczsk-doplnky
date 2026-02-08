# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from .provider import TvheadendContentProvider
from .http_handler import TvheadendHTTPRequestHandler

def main(addon):
	# Dôležité: bez http_cls sa TvheadendHTTPRequestHandler nezaregistruje
	# a potom URL v userbouquete (127.0.0.1:18888/tvheadend/playlive/...) dávajú 404.
	return ArchivCZSKContentProvider(TvheadendContentProvider, addon, http_cls=TvheadendHTTPRequestHandler)
