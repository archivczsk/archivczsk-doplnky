# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import WebshareContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(WebshareContentProvider, addon)
