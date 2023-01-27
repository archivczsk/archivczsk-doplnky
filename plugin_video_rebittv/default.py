# -*- coding: utf-8 -*-

import sys, os
try:
	sys.path.append( os.path.dirname(__file__) )
except:
	pass

import util
import xbmcprovider
import uuid

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from rebittv_provider import RebitTVContentProvider

# #################################################################################################

__scriptid__ = 'plugin.video.rebittv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)

settings = {'quality':__addon__.getSetting('quality')}

provider = RebitTVContentProvider( username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), device_name=__addon__.getSetting('device_name'), data_dir=__addon__.getAddonInfo('profile'), session=session )

xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
