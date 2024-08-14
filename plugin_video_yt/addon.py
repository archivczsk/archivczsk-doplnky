# -*- coding: UTF-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import YoutubeContentProvider

# #################################################################################################

def main(addon):
	cp = YoutubeContentProvider(addon.settings, data_dir=addon.get_info('data_path'))
	return ArchivCZSKContentProvider(cp, addon)
