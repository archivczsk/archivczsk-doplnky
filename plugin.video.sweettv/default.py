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
from sweettv_provider import SweetTVContentProvider

# #################################################################################################

__scriptid__ = 'plugin.video.sweettv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)

settings = {'quality':__addon__.getSetting('quality')}

device_id = __addon__.getSetting( 'device_id' )

if device_id == '':
	device_id = str( uuid.uuid4() )
	__addon__.setSetting( 'device_id', device_id )

provider = SweetTVContentProvider( username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), device_id=device_id, data_dir=__addon__.getAddonInfo('profile'), session=session )

xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
