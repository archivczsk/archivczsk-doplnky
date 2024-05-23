import os
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .http_handler import iVysilaniHTTPRequestHandler
from .provider import iVysilaniContentProvider

# #################################################################################################

def main(addon):
	resources_dir = os.path.join(addon.get_info('path'), 'resources')
	cp = iVysilaniContentProvider(addon.settings, data_dir=addon.get_info('data_path'), resources_dir=resources_dir, http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id))
	archivCZSKHttpServer.registerRequestHandler(iVysilaniHTTPRequestHandler(cp, addon))
	return ArchivCZSKContentProvider(cp, addon)
