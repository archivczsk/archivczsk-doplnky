# -*- coding: utf-8 -*-

import sys, os, uuid

from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.compat import XBMCCompatInterface

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer

from .magiogo_provider import magiogoContentProvider
from .http_handler import MagioGoTvHTTPRequestHandler

# #################################################################################################

__scriptid__ = 'plugin.video.magiogo'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)

device_id = __addon__.getSetting( 'deviceid' )

if device_id == '':
	device_id = str( uuid.uuid4() )
	__addon__.setSetting( 'deviceid', device_id )

def magiogo_run(session, params):
	provider = magiogoContentProvider(username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), device_id=device_id, data_dir=__addon__.getAddonInfo('profile'), session=session)
	settings = {'quality':__addon__.getSetting('quality')}
	XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)


def main(addon):
	request_handler = MagioGoTvHTTPRequestHandler()
	archivCZSKHttpServer.registerRequestHandler(request_handler)
	log.info("Magio GO http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint(request_handler))

	return XBMCCompatInterface(magiogo_run)
