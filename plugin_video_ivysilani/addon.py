from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.compat import XBMCCompatInterface
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from .lib.ivysilani_main import iVysilaniContentProvider, iVysilaniContentProviderHelper_Init

def ivysilani_run(session, params, addon):
	settings = {'quality':addon.getSetting('quality')}
	XBMCMultiResolverContentProvider(iVysilaniContentProvider(http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id)), settings, addon, session).run(params)


def main(addon):
	cp = iVysilaniContentProviderHelper_Init(addon.settings, data_dir=addon.get_info('data_path'), http_endpoint=archivCZSKHttpServer.getAddonEndpoint(addon.id))
	archivCZSKHttpServer.registerRequestHandler(DashHTTPRequestHandler(cp, addon))
	return XBMCCompatInterface(ivysilani_run, addon)
