# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .provider import OrangeTVContentProvider

# #################################################################################################

def main(addon):
	# import data from old config options
	for old_name, new_name in [ ('orangetvuser', 'username'), ('orangetvpwd', 'password') ]:
		old_value = addon.get_setting(old_name)
		new_value = addon.get_setting(new_name)

		if not new_value and old_value:
			addon.set_setting(new_name, old_value)
			addon.set_setting(old_name, '')

	cp = OrangeTVContentProvider(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id), bgservice=addon.bgservice)
	archivCZSKHttpServer.registerRequestHandler(PlayliveTVHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
