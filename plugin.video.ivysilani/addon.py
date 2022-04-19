import util, xbmcprovider
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
__scriptid__ = 'plugin.video.ivysilani'
__scriptname__ = 'ivysilani.cz'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString

sys.path.append(os.path.join (os.path.dirname(__file__), 'resources', 'lib'))
import ivysilani_main
settings = {'quality':__addon__.getSetting('quality')}

xbmcprovider.XBMCMultiResolverContentProvider(ivysilani_main.iVysilaniContentProvider(), settings, __addon__, session).run(params)
