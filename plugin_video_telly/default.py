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
from telly_provider import tellyContentProvider

# #################################################################################################

__scriptid__ = 'plugin.video.telly'
__scriptname__ = 'telly'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString

provider = tellyContentProvider( data_dir=__addon__.getAddonInfo('profile'), session=session )
settings = {'quality':__addon__.getSetting('quality')}

xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
