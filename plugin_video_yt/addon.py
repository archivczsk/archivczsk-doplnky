# -*- coding: UTF-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import YoutubeContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(YoutubeContentProvider, addon)
