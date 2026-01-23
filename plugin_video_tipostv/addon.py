# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from .provider import TiposTVContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(TiposTVContentProvider, addon)
