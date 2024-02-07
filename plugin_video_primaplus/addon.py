# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import PrimaPlusContentProvider

# #################################################################################################

def main(addon):
	cp = PrimaPlusContentProvider(addon.settings, data_dir=addon.get_info('data_path'))
	return ArchivCZSKContentProvider(cp, addon)
