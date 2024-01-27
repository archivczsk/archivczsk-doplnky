# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2012 Libor Zoubek
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

import re, os, traceback
from Plugins.Extensions.archivCZSK.engine import client

try:
	from urllib2 import urlopen, Request, HTTPError
except:
	from urllib.request import urlopen, Request
	from urllib.error import HTTPError

from threading import Lock

from tools_xbmc.contentprovider import xbmcprovider
from tools_xbmc.contentprovider.provider import ResolveException
from tools_xbmc.tools import util, search, xbmcutil
from tools_xbmc.compat import XBMCCompatInterface

from .providers import fastshare, webshare

settings = {}
providers = {}

def online_files_run(session, params, addon):
	global settings, providers
	settings = {}
	providers = {}

	def search_cb(what):
		def paralel_search(search):
			def do_search(p,what):
				res = []
				try:
					result = p.provider.search(what)
					for item in result:
						item['title'] = '[%s] %s' % (p.provider.name,item['title'])
						if item['type'] == 'next':
							item['type'] = 'dir'
							item['title'] = '[%s] %s >>' % (p.provider.name,addon.getLocalizedString(30063))
				except:
					traceback.print_exc()
				with lock:
					p.list(result)
			lock = Lock()
			util.run_parallel_in_threads(do_search, search)

		searches = []
		for key in list(providers.keys()):
			p = providers[key]
			searches.append((p,what))
		paralel_search(searches)

	def icon(provider):
		icon_file = os.path.join(addon.get_info('path'), 'resources', 'icons', provider + '.png')
		if not os.path.isfile(icon_file):
			return 'DefaultFolder.png'
		return icon_file

	def root():
		search.item()
		for provider in list(providers.keys()):
			xbmcutil.add_dir(provider, {'cp':provider}, icon(provider))
		return

	def webshare_filter(item):
		ext_filter = addon.getSetting('webshare_ext-filter').split(',')
		ext_filter =  ['.'+f.strip() for f in ext_filter]
		extension = os.path.splitext(item['title'])[1]
		if extension in ext_filter:
			return False
		return True

	if addon.getSetting('fastshare_enabled') == 'true':
		p = fastshare.FastshareContentProvider(username='', password='', tmp_dir=addon.getAddonInfo('data_path'))
		extra = {
					'vip':'0',
					'keep-searches':addon.getSetting('fastshare_keep-searches')
		}
		extra.update(settings)
		providers[p.name] = xbmcprovider.XBMCLoginOptionalContentProvider(p, extra, addon, session)

	if addon.getSetting('webshare_enabled') == 'true':
		p = webshare.WebshareContentProvider(username=addon.getSetting('webshare_user'), password=addon.getSetting('webshare_pass'), filter=webshare_filter)
		extra = {
				'vip':'0',
				'keep-searches':addon.getSetting('webshare_keep-searches')
		}
		extra.update(settings)
		providers[p.name] = xbmcprovider.XBMCLoginOptionalContentProvider(p, extra, addon, session)

	if params == {}:
		root()
	elif 'cp' in list(params.keys()):
		cp = params['cp']
		if cp in list(providers.keys()):
			providers[cp].run(params)
	else:
		search.main(session, addon, 'search_history', params, search_cb)

def main(addon):
	return XBMCCompatInterface(online_files_run, addon)
