# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler

from .provider import TvheadendContentProvider

# FIX 0.57.0 (skyjet PR #22 review #10): custom http_handler.py odstránený.
# Framework PlayliveTVHTTPRequestHandler robí presne to isté (base64 decode
# channel key, redirect na stream URL) + má built-in 15-min LRU cache pre
# opakované playback-y. Provider implementuje len get_url_by_channel_key(uuid)
# ktorý vráti TVH stream URL pre už dekódovaný channel UUID.


def main(addon):
	return ArchivCZSKContentProvider(TvheadendContentProvider, addon,
	                                  http_cls=PlayliveTVHTTPRequestHandler)
