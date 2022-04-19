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
from antiktv import antiktvContentProvider

# #################################################################################################

__scriptid__ = 'plugin.video.antiktv'
__scriptname__ = 'antiktv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString

#settings = {'quality':__addon__.getSetting('quality')}
settings = {}

provider = antiktvContentProvider( username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), device_id=__addon__.getSetting( 'device_id' ), region=__addon__.getSetting( 'region' ), session=session )

xbmcprovider.XBMCLoginRequiredContentProvider(provider, settings, __addon__, session).run(params)
