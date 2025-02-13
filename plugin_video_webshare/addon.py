# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import WebshareContentProvider

# #################################################################################################

def main(addon):
	cp = WebshareContentProvider(addon.settings, data_dir=addon.get_info('data_path'), bgservice=addon.bgservice)
	return ArchivCZSKContentProvider(cp, addon)
