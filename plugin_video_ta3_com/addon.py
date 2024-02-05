# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import Ta3ContentProvider

# #################################################################################################

def main(addon):
	cp = Ta3ContentProvider(addon.settings, data_dir=addon.get_info('data_path'))
	return ArchivCZSKContentProvider(cp, addon)
