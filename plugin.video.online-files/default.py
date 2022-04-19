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
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine import client

try:
	from urllib2 import urlopen, Request, HTTPError
except:
	from urllib.request import urlopen, Request
	from urllib.error import HTTPError

__scriptid__ = 'plugin.video.online-files'
__scriptname__ = 'Soubory Online'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString
__settings__ = __addon__.getSetting

sys.path.append(os.path.join (os.path.dirname(__file__), 'resources', 'lib'))

from threading import Lock
import util, search

import xbmcutil
import hellspy, ulozto, fastshare, webshare
import xbmcprovider

from provider import ResolveException

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
						item['title'] = '[%s] %s >>' % (p.provider.name,__language__(30063))
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

def ulozto_filter(item):
		ext_filter = __settings__('ulozto_ext-filter').split(',')
		ext_filter = ['.' + f.strip() for f in ext_filter]
		extension = os.path.splitext(item['title'])[1]
		if extension in ext_filter:
				return False
		return True

def webshare_filter(item):
	ext_filter = __settings__('webshare_ext-filter').split(',')
	ext_filter =  ['.'+f.strip() for f in ext_filter]
	extension = os.path.splitext(item['title'])[1]
	if extension in ext_filter:
		return False
	return True

class XBMCUloztoContentProvider(xbmcprovider.XBMCLoginOptionalContentProvider):

	def __init__(self, provider, settings, addon, session):
		xbmcprovider.XBMCLoginOptionalContentProvider.__init__(self, provider, settings, addon, session)
		self.check_setting_keys(['vip', 'search-type'])
		search_type = ''
		search_types = {'0':'', '1':'media=video&', '2':'media=image&', '3':'media=music&', '4':'media=document&'}
		print( 'setting is ' + str(settings['search-type']) )
		if settings['search-type'] in list(search_types.keys()):
			search_type = search_types[settings['search-type']]
		provider.search_type = search_type

	def resolve(self,url):
		item = self.provider.video_item()
		item.update({'url':url,'vip':True})
		if not self.ask_for_account_type():
			# user does not want to use VIP at this time
			item.update({'vip':False})
		else:
			if not self.provider.login():
				client.showInfo(xbmcutil.__lang__(30011))
				return
		try:
			return self.provider.resolve(item,captcha_cb=self.solve_captcha)
		except ResolveException as e:
			self._handle_exc(e)

	def solve_captcha(self,params):
		snd = os.path.join(self.addon.getAddonInfo('profile'),'sound.wav')
		util.save_to_file(params['snd'], snd)
		try:
			sndfile = open(snd, 'rb').read()
			url = 'http://m217-io.appspot.com/ulozto'
			headers = {'Content-Type': 'audio/wav'}
			req = Request(url, sndfile, headers)
			response = urlopen(req, timeout=60)
			data = response.read().decode('utf-8')
			response.close()
		except HTTPError:
			traceback.print_exc()
			data = ''
		if not data:
			return self.ask_for_captcha(params)
		return data

class XBMCHellspyContentProvider(xbmcprovider.XBMCLoginRequiredContentProvider):

	def render_default(self, item):
		params = self.params()
		if item['type'] == 'top':
			params.update({'list':item['url']})
			xbmcutil.add_dir(item['title'], params, xbmcutil.icon('top.png'))

	def render_video(self, item):
		params = self.params()
		params.update({'to-downloads':item['url']})
		item['menu'] = {__language__(30056):params}
		return xbmcprovider.XBMCLoginRequiredContentProvider.render_video(self, item)

	def run_custom(self, params):
		if 'to-downloads' in list(params.keys()):
			self.provider.to_downloads(params['to-downloads'])

settings = {}

providers = {}

if __settings__('ulozto_enabled'):
	p = ulozto.UloztoContentProvider(__settings__('ulozto_user'), __settings__('ulozto_pass'), filter=ulozto_filter)
	extra = {
			'vip':__settings__('ulozto_usevip'),
			'keep-searches':__settings__('ulozto_keep-searches'),
			'search-type':__settings__('ulozto_search-type')
	}
	extra.update(settings)
	providers[p.name] = XBMCUloztoContentProvider(p, extra, __addon__, session)

if __settings__('hellspy_enabled'):
	p = hellspy.HellspyContentProvider(__settings__('hellspy_user'), __settings__('hellspy_pass'), site_url=__settings__('hellspy_site_url'))
	extra = {
			'keep-searches':__settings__('hellspy_keep-searches')
	}
	extra.update(settings)
	providers[p.name] = XBMCHellspyContentProvider(p, extra, __addon__, session)

if __settings__('fastshare_enabled'):
	p = fastshare.FastshareContentProvider(username='', password='', tmp_dir=__addon__.getAddonInfo('profile'))
	extra = {
				'vip':'0',
				'keep-searches':__settings__('fastshare_keep-searches')
	}
	extra.update(settings)
	providers[p.name] = xbmcprovider.XBMCLoginOptionalContentProvider(p, extra, __addon__, session)

if __settings__('webshare_enabled'):
	p = webshare.WebshareContentProvider(username=__settings__('webshare_user'), password=__settings__('webshare_pass'),filter=webshare_filter)
	extra = {
			'vip':'0',
			'keep-searches':__settings__('webshare_keep-searches')
	}
	extra.update(settings)
	providers[p.name] = xbmcprovider.XBMCLoginOptionalContentProvider(p,extra,__addon__, session)

def icon(provider):
	icon_file = os.path.join(__addon__.get_info('path'), 'resources', 'icons', provider + '.png')
	if not os.path.isfile(icon_file):
		return 'DefaultFolder.png'
	return icon_file

def root():
	search.item()
	for provider in list(providers.keys()):
		xbmcutil.add_dir(provider, {'cp':provider}, icon(provider))
	return

if params == {}:
	root()
elif 'cp' in list(params.keys()):
	cp = params['cp']
	if cp in list(providers.keys()):
		providers[cp].run(params)
else:
	search.main(session, __addon__, 'search_history', params, search_cb)
