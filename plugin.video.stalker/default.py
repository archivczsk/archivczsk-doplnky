# -*- coding: utf-8 -*-

from __future__ import print_function
import sys, os, uuid
try:
	sys.path.append( os.path.dirname(__file__)	)
except:
	pass

import util
import xbmcprovider

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from stalker_provider import stalkerContentProvider

# #################################################################################################

__scriptid__ = 'plugin.video.stalker'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString
settings = {}

provider = stalkerContentProvider( data_dir=__addon__.getAddonInfo('profile'), session=session )

xbmcprovider.XBMCLoginRequiredContentProvider(provider, settings, __addon__, session).run(params)
