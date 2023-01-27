# -*- coding: utf-8 -*-

import sys, os
try:
	sys.path.append( os.path.dirname(__file__) )
except:
	pass

import util
import xbmcprovider

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from sledovanitv_provider import SledovaniTVContentProvider

# #################################################################################################

__scriptid__ = 'plugin.video.sledovanitv'
__scriptname__ = 'sledovanitv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString

settings = {'quality':__addon__.getSetting('quality')}

serialid = __addon__.getSetting( 'serialid' )
if not serialid or len(serialid) == 0:
	import random
	serialid = ''.join(random.choice('0123456789abcdef') for n in range(40))
	__addon__.setSetting("serialid", serialid)

provider = SledovaniTVContentProvider( username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), pin=__addon__.getSetting('pin'), serialid=serialid, data_dir=__addon__.getAddonInfo('profile'), session=session )

xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
