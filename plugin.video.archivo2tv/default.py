# -*- coding: utf-8 -*-

import sys, os
try:
	sys.path.append( os.path.dirname(__file__) )
except:
	pass

import util
import xbmcprovider

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from o2tv_provider import O2tvContentProvider

# #################################################################################################

__scriptid__ = 'plugin.video.archivo2tv'
__scriptname__ = 'archivo2tv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString

settings = {'quality':__addon__.getSetting('quality')}

device_id = __addon__.getSetting( 'deviceid' )
if not device_id or len(device_id) == 0:
	import random, string
	device_id = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(15))
	__addon__.setSetting("deviceid", device_id)

provider = O2tvContentProvider( username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), device_id=device_id, data_dir=__addon__.getAddonInfo('profile'), session=session )

xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
