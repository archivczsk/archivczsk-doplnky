# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import StreamCinemaContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(StreamCinemaContentProvider, addon)
