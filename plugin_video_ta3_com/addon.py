# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import Ta3ContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(Ta3ContentProvider, addon)
