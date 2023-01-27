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
from magiogo_provider import magiogoContentProvider

# #################################################################################################

__scriptid__ = 'plugin.video.magiogo'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString

device_id = __addon__.getSetting( 'deviceid' )

if device_id == '':
	device_id = str( uuid.uuid4() )
	__addon__.setSetting( 'deviceid', device_id )

provider = magiogoContentProvider( username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), device_id=device_id, data_dir=__addon__.getAddonInfo('profile'), session=session )
settings = {'quality':__addon__.getSetting('quality')}

xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
