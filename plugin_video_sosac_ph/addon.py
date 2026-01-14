# -*- coding: utf-8 -*-
import os
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import SosacContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(SosacContentProvider, addon, icons_dir=os.path.join(addon.get_info('path'), 'resources', 'icons'))
