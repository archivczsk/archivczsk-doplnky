# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import StreamCinemaContentProvider

# #################################################################################################

def main(addon):
	cp = StreamCinemaContentProvider(addon.settings, data_dir=addon.get_info('data_path'))
	return ArchivCZSKContentProvider(cp, addon)
