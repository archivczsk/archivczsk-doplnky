# -*- coding: utf-8 -*-
import os
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import SosacContentProvider

# #################################################################################################

def main(addon):
	cp = SosacContentProvider(addon.settings, data_dir=addon.get_info('data_path'), icons_dir=os.path.join(addon.get_info('path'), 'resources', 'icons'))
	return ArchivCZSKContentProvider(cp, addon)
