# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import MarkizaContentProvider

# #################################################################################################

def main(addon):
	cp = MarkizaContentProvider(addon.settings, data_dir=addon.get_info('profile'))
	return ArchivCZSKContentProvider(cp, addon)
