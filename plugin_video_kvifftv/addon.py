# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import KviffTvContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(KviffTvContentProvider, addon)
