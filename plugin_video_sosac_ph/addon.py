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

from Plugins.Extensions.archivCZSK.engine import client

from tools_xbmc.contentprovider import xbmcprovider
from tools_xbmc.contentprovider.provider import ResolveException
from tools_xbmc.resolver import resolver
from tools_xbmc.compat import XBMCCompatInterface

import re
from .sosac import SosacContentProvider

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
				idx = client.getListInput(self.session, stream_list, self.addon.getLocalizedString("Select stream"))
				if idx == -1:
					return None
				return resolved[idx]

		item = self.provider.video_item()
		item.update({'url':url})
		try:
			return self.provider.resolve(item, select_cb=select_cb)
		except ResolveException as e:
			self._handle_exc(e)


def sosac_run(session, params, addon):
	settings = {'quality':addon.getSetting('quality'), 'subs':addon.getSetting('subs') == 'true'}
	reverse_eps = addon.getSetting('order-episodes') == '0'

	sosac = SosacContentProvider(reverse_eps=reverse_eps)
	sosac.streamujtv_user = addon.getSetting('streamujtv_user')
	sosac.streamujtv_pass = addon.getSetting('streamujtv_pass')
	sosac.streamujtv_location = addon.getSetting('streamujtv_location')

	SosacProvider(sosac, settings, addon, session).run(params)

def main(addon):
	return XBMCCompatInterface(sosac_run, addon)
