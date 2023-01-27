# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2013 Libor Zoubek + jondas
# *
# *
# *	 This Program is free software; you can redistribute it and/or modify
# *	 it under the terms of the GNU General Public License as published by
# *	 the Free Software Foundation; either version 2, or (at your option)
# *	 any later version.
# *
# *	 This Program is distributed in the hope that it will be useful,
# *	 but WITHOUT ANY WARRANTY; without even the implied warranty of
# *	 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *	 GNU General Public License for more details.
# *
# *	 You should have received a copy of the GNU General Public License
# *	 along with this program; see the file COPYING.	 If not, write to
# *	 the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *	 http://www.gnu.org/copyleft/gpl.html
# *
# */

sys.path.append( os.path.join ( os.path.dirname(__file__),'resources','lib') )
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine import client


import re
import util,xbmcprovider,xbmcutil, resolver
from provider import ResolveException
from sosac import SosacContentProvider

__scriptid__   = 'plugin.video.sosac.ph'
__scriptname__ = 'sosac.ph'
__addon__	   = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__   = __addon__.getLocalizedString
__set__		  = __addon__.getSetting

settings = {'quality':__addon__.getSetting('quality'), 'subs':__set__('subs') == 'true'}
reverse_eps = __set__('order-episodes') == '0'

sosac = SosacContentProvider(reverse_eps=reverse_eps)
sosac.streamujtv_user = __set__('streamujtv_user')
sosac.streamujtv_pass = __set__('streamujtv_pass')
sosac.streamujtv_location = __set__('streamujtv_location')


print("Running sosac provider with params:", params)
#xbmcprovider.XBMCMultiResolverContentProvider2(sosac,settings,__addon__, session).run(params)

class SosacProvider(xbmcprovider.XBMContentProvider):

	def __init__(self, provider, settings, addon, session):
		xbmcprovider.XBMContentProvider.__init__(self, provider, settings, addon, session)
		self.check_setting_keys(['quality'])

	def resolve(self, url):
		def select_cb(resolved):
			resolved = resolver.filter_by_quality(resolved, self.settings['quality'] or '0')
			if len(resolved) == 1:
				return resolved[0]
			else:
				stream_list = ['[%s]%s'%(s['quality'],s['lang']) for s in resolved]
				idx = client.getListInput(self.session, stream_list, _("Select stream"))
				if idx == -1:
					return None
				return resolved[idx]

		item = self.provider.video_item()
		item.update({'url':url})
		try:
			return self.provider.resolve(item, select_cb=select_cb)
		except ResolveException as e:
			self._handle_exc(e)

SosacProvider(sosac,settings,__addon__, session).run(params)

