# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2013 Maros Ondrasek
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
from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.compat import XBMCCompatInterface
from .joj import JojContentProvider

class XBMCJojContentProvider(XBMCMultiResolverContentProvider):
	def render_default(self, item):
		if item['type'] == 'showoff':
			item['title'] = item['title'] + '  (Nevys)'
		elif item['type'] == "showon7d":
			item['title'] = item['title'] + ' (7d)'
		if item['type'] == 'topvideo' or item['type'] == 'newvideo':
			self.render_video(item)
		else:
			self.render_dir(item)


def joj_run(session, params, addon):
	settings = {'quality':addon.getSetting('quality')}
	provider = JojContentProvider()
	XBMCJojContentProvider(provider, settings, addon, session).run(params)

def main(addon):
	return XBMCCompatInterface(joj_run, addon)
