from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.compat import XBMCCompatInterface
from .lib.ivysilani_main import iVysilaniContentProvider

def ivysilani_run(session, params, addon):
	settings = {'quality':addon.getSetting('quality')}
	XBMCMultiResolverContentProvider(iVysilaniContentProvider(), settings, addon, session).run(params)


def main(addon):
	return XBMCCompatInterface(ivysilani_run, addon)
