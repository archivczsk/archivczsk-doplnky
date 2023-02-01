# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .provider import OrangeTVContentProvider
from .http_handler import OrangeTVHTTPRequestHandler

# #################################################################################################

def main(addon):
	# import data from old config options
	for old_name, new_name in [ ('orangetvuser', 'username'), ('orangetvpwd', 'password') ]:
		old_value = addon.get_setting(old_name)
		new_value = addon.get_setting(new_name)

		if not new_value and old_value:
			addon.set_setting(new_name, old_value)
			addon.set_setting(old_name, '')

	cp = OrangeTVContentProvider(addon.settings, data_dir=addon.get_info('profile'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id), bgservice=addon.bgservice)
	archivCZSKHttpServer.registerRequestHandler(OrangeTVHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
