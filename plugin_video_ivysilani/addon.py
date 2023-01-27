from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.compat import XBMCCompatInterface
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from .lib.ivysilani_main import iVysilaniContentProvider

__scriptid__ = 'plugin.video.ivysilani'
__scriptname__ = 'ivysilani.cz'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString


def ivysilani_run(session, params):
	settings = {'quality':__addon__.getSetting('quality')}
	XBMCMultiResolverContentProvider(iVysilaniContentProvider(), settings, __addon__, session).run(params)


def main(addon):
	return XBMCCompatInterface(ivysilani_run)
