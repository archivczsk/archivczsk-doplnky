# -*- coding: utf-8 -*-

from __future__ import print_function
import sys, os
try:
	sys.path.append( os.path.dirname(__file__)	)
except:
	pass

import util
import xbmcprovider

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from orangetv_provider import orangetvContentProvider

# #################################################################################################

__scriptid__ = 'plugin.video.orangetv'
__scriptname__ = 'orangetv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString

settings = {'quality':__addon__.getSetting('quality')}

provider = orangetvContentProvider( username=__addon__.getSetting('orangetvuser'), password=__addon__.getSetting('orangetvpwd'), device_id=__addon__.getSetting( 'deviceid' ), data_dir=__addon__.getAddonInfo('profile'), session=session )

xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
