# -*- coding: utf-8 -*-
"""
plugin.video.e2m3u2bouquet — ArchivCZSK addon entry point.

Convert IPTV M3U playlists to Enigma2 bouquets with XMLTV EPG injection.
Optional Tvheadend integration for stream auth + metadata enrichment.

Pôvodne extract z plugin.video.tvheadend 0.57.0 (skyjet PR #22 review #10/#11)
ako samostatný doplnok.
"""

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from .provider import E2M3U2BouquetContentProvider


def main(addon):
	return ArchivCZSKContentProvider(E2M3U2BouquetContentProvider, addon)
