# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import IdnesTvContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(IdnesTvContentProvider, addon)
