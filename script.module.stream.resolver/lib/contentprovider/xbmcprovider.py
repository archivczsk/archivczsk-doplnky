# -*- coding: utf-8 -*-
# *		 Copyright (C) 2012 Libor Zoubek
# *				modified by mx3L
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

import sys, os, re, traceback, util, xbmcutil, resolver, time
from Plugins.Extensions.archivCZSK.engine import client
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

from provider import ResolveException
from resolver import rslog

try:
	basestring
	is_py3 = False
except NameError:
	unicode = str
	is_py3 = True
	
class XBMContentProvider(object):
	'''
	ContentProvider class provides an internet content. It should NOT have any xbmc-related imports
	and must be testable without XBMC runtime. This is a basic/dummy implementation.
	'''

	def __init__(self, provider, settings, addon, session):
		'''
		XBMContentProvider constructor
		Args:
			name (str): name of provider
		'''
		self.provider = provider
		self.settings = settings
		self.addon = addon
		self.addon_id = addon.get_info('id')
		self.session = session

	def check_setting_keys(self, keys):
		for key in keys:
			if not key in list(self.settings.keys()):
				raise Exception('Invalid settings passed - [' + key + '] setting is required');


	def params(self):
		return {'cp':self.provider.name}

	def run(self, params):
		rslog.logDebug("XBMC run params=%s"%params)
		if params == {} or params == self.params():
			return self.root()
		elif 'list' in list(params.keys()):
			self.list(self.provider.list(params['list']))
		elif 'play' in list(params.keys()):
			return self.play(params)
		elif 'search-list' in list(params.keys()):
			return self.search_list()
		elif 'search' in list(params.keys()):
			return self.do_search2(params['search'], params)
		elif 'search-remove' in list(params.keys()):
			return self.search_remove(params['search-remove'])
		elif 'search-edit' in list(params.keys()):
			return self.search_edit(params['search-edit'])
		elif 'stats' in list(params.keys()):
			if 'stats' in self.provider.capabilities():
				itm = None
				if 'item' in list(params.keys()):
					itm = params['item']
				rslog.logDebug("XBMC run stats '%s'"%params['stats'])
				self.provider.stats(itm, params['stats'])
			else:
				rslog.logDebug("'%s' dont have capability 'stats'"%self.provider)
		elif 'trakt' in list(params.keys()):
			if 'trakt' in self.provider.capabilities():
				itm = None
				if 'item' in list(params.keys()):
					itm = params['item']
				rslog.logDebug("XBMC run trakt '%s'"%params['trakt'])
				# @TODO how to return data to plugin ??? i dont know how for now
				return self.provider.trakt(itm, params['trakt'])
			else:
				rslog.logDebug("'%s' dont have capability 'trakt'"%self.provider)
				return None
		elif self.run_custom:
			return self.run_custom(params)

	def search_list(self):
		params = self.params()
		params.update({'search':''})
		xbmcutil.add_search_item(xbmcutil.__lang__(30004), params, xbmcutil.icon('search.png'))
		maximum = 10
		try:
			maximum = int(self.settings['keep-searches'])
		except:
			pass
		for what in xbmcutil.get_searches(self.addon, self.provider.name, maximum):
			params = self.params()
			menuItems = self.params()
			menuItems2 = self.params()
			params['search'] = what
			menuItems['search-remove'] = what
			menuItems2['search-edit'] = what
			xbmcutil.add_dir(what, params, menuItems={u'Remove':menuItems,u'Edit':menuItems2})

	def search_remove(self, what):
		xbmcutil.remove_search(self.addon, self.provider.name, what)
		client.refresh_screen()

	def search_edit(self, what):
		try:
			replacement = client.getTextInput(self.session, xbmcutil.__lang__(30003), what)
		except ValueError:
			client.showInfo("Please install new version of archivCZSK")
		if replacement != '':
			xbmcutil.edit_search(self.addon, self.provider.name, what, replacement)
			client.refresh_screen()

	def do_search2(self, what, params):
		if what == '':
			what = client.getTextInput(self.session, xbmcutil.__lang__(30003))
		if not what == '':
			maximum = 10
			try:
				maximum = int(self.settings['keep-searches'])
			except:
				util.error('Unable to parse convert addon setting to number')
				pass
			if 'search-no-history' in params and params['search-no-history']:
				# do nothing dont save history
				a = 'nothing'
			else:
				xbmcutil.add_search(self.addon, self.provider.name, what, maximum)
			self.search(what)
	def do_search(self, what):
		if what == '':
			what = client.getTextInput(self.session, xbmcutil.__lang__(30003))
		if not what == '':
			maximum = 20
			try:
				maximum = int(self.settings['keep-searches'])
			except:
				util.error('Unable to parse convert addon setting to number')
				pass
			xbmcutil.add_search(self.addon, self.provider.name, what, maximum)
			self.search(what)

	def root(self):
		if 'search' in self.provider.capabilities():
			params = self.params()
			params.update({'search-list':''})
			xbmcutil.add_search_folder(xbmcutil.__lang__(30003), params, xbmcutil.icon('search.png'))
		self.list(self.provider.categories())

	def get_subtitle(self, url, headers=None):
		if url and headers:
			try:
				import hashlib
				local = os.path.join("/tmp", 'xbmc_subs_%s.srt'%int(hashlib.md5(url).hexdigest(), 16))
				if not os.path.isfile(local):
					data = util.request(url, headers)
					with open(local, "w") as f:
						f.write(data)
				return local
			except Exception:
				traceback.print_exc()
		return url

	def play(self, params):
		data = self.resolve(params['play'])
		if data is not None:
			if isinstance(data, type([])):
				for item in data:
					xbmcutil.add_play(params['title'],
							item['title'],
							item['quality'],
							item['url'],
							subs=self.get_subtitle(item['subs'], item.get('headers')),
							filename=params['title'],
							headers=item.get('headers',dict()),
							lang=item.get('lang',''),
							resolveTitle = item.get('resolveTitle',''),
							customTitle = item.get('customTitle',''),
							customFname = item.get('customFname',''),
							addonDataItem = item.get('customDataItem',''),
							player_settings = item.get('playerSettings'))
			else:
				xbmcutil.add_play(params['title'],
						data['title'],
						data['quality'],
						data['url'],
						subs=self.get_subtitle(data['subs'], data.get('headers')),
						filename=params['title'],
						headers=data.get('headers',dict()),
						lang=data.get('lang',''),
						resolveTitle = data.get('resolveTitle',''),
						customTitle = data.get('customTitle',''),
						customFname = data.get('customFname',''),
						addonDataItem = data.get('customDataItem',''),
						player_settings = data.get('playerSettings'))




	def _handle_exc(self, e):
		try:
			msg = e.message
		except:
			msg = str(e)
			
		if msg.find('$') == 0:
			try:
				msg = self.addon.getLocalizedString(int(msg[1:]))
			except:
				try:
					msg = xbmcutil.__lang__(int(msg[1:]))
				except:
					pass
		client.showError(msg)


	def resolve(self, url):
		item = self.provider.video_item()
		item.update({'url':url})
		try:
			return self.provider.resolve(item)
		except ResolveException as e:
			self._handle_exc(e)


	def search(self, keyword):
		self.list(self.provider.search(keyword))

	def list(self, items):
		for item in items:
			params = self.params()
			if item['type'] == 'dir':
				self.render_dir(item)
			elif item['type'] == 'next':
				params.update({'list':item['url']})
				xbmcutil.add_dir(xbmcutil.__lang__(30007), params, xbmcutil.icon('next.png'))
			elif item['type'] == 'prev':
				params.update({'list':item['url']})
				xbmcutil.add_dir(xbmcutil.__lang__(30008), params, xbmcutil.icon('prev.png'))
			elif item['type'] == 'new':
				params.update({'list':item['url']})
				xbmcutil.add_dir(xbmcutil.__lang__(30012), params, xbmcutil.icon('new.png'))
			elif item['type'] == 'top':
				params.update({'list':item['url']})
				xbmcutil.add_dir(xbmcutil.__lang__(30013), params, xbmcutil.icon('top.png'))
			elif item['type'] == 'video':
				self.render_video(item)
			else:
				self.render_default(item)

	def render_default(self, item):
		raise Exception("Unable to render item " + item)
	
	def _localize(self, text):
		def _localize(m):
			try:
				return self.addon.getLocalizedString(int(m.group(1)))
			except Exception:
				return m.group(1)
		if not isinstance( text, str ):
			text = text.decode('utf-8')
		return re.sub(r'\$(\d{4,5})', _localize, text)

	def render_dir(self, item):
		params = self.params()
		params.update({'list':item['url']})
		title = item['title']
		img = None
		if 'img' in list(item.keys()):
			img = item['img']
		title = self._localize(title)
		menuItems = {}
		if 'menu' in list(item.keys()):
			for ctxtitle, value in item['menu'].items():
				ctxtitle = self._localize(ctxtitle)
				menuItems[ctxtitle] = value
		xbmcutil.add_dir(title, 
						 params, 
						 img, 
						 infoLabels=self._extract_infolabels(item), 
						 menuItems=menuItems,
						 addonDataItem = item.get('customDataItem',''))

	def _extract_infolabels(self, item):
		infoLabels = {}
		for label in ['plot', 'year', 'genre', 'rating', 'director', 'votes', 'cast', 'trailer', 'duration', 'videoid', 'videowidth']:
			if label in list(item.keys()):
				infoLabels[label] = util.decode_html(item[label])
		return infoLabels

	def render_video(self, item):
		params = self.params()
		params.update({'play':item['url'], 'title':item['title']})
		downparams = self.params()
		downparams.update({'name':item['title'], 'down':item['url']})
		def_item = self.provider.video_item()
		if item['size'] == def_item['size']:
			item['size'] = ''
		else:
			item['size'] = ' (%s)' % item['size']
		title = '%s%s' % (item['title'], item['size'])
		menuItems = {}
		if 'menu' in list(item.keys()):
			for ctxtitle, value in item['menu'].items():
				if ctxtitle.find('$') == 0:
					try:
						ctxtitle = self.addon.getLocalizedString(int(ctxtitle[1:]))
					except:
						pass
				menuItems[ctxtitle] = value
		xbmcutil.add_video(title,
			params,
			item['img'],
			infoLabels=self._extract_infolabels(item),
			menuItems=menuItems,
			addonDataItem = item.get('customDataItem','')
		)

	def categories(self):
		self.list(self.provider.categories(keyword))

class XBMCMultiResolverContentProvider(XBMContentProvider):

	def __init__(self, provider, settings, addon, session):
		XBMContentProvider.__init__(self, provider, settings, addon, session)
		self.check_setting_keys(['quality'])

	def resolve(self, url):
		def select_cb(resolved):
			resolved = resolver.filter_by_quality(resolved, self.settings['quality'] or '0')
			if len(resolved) == 1:
				return resolved[0]
			return resolved

		item = self.provider.video_item()
		item.update({'url':url})
		try:
			return self.provider.resolve(item, select_cb=select_cb)
		except ResolveException as e:
			self._handle_exc(e)


class XBMCLoginRequiredContentProvider(XBMContentProvider):

	def root(self):
		if not self.provider.login():
			client.showInfo(xbmcutil.__lang__(30011))
		else:
			return XBMContentProvider.root(self)

class XBMCLoginOptionalContentProvider(XBMContentProvider):

	def __init__(self, provider, settings, addon, session):
		XBMContentProvider.__init__(self, provider, settings, addon, session)
		self.check_setting_keys(['vip'])

	def ask_for_captcha(self, params):
		img = params['img']
		if is_py3 ==False and isinstance(img, unicode):
			img = img.encode('utf-8')
		return client.getCaptcha(self.session, img)

	def ask_for_account_type(self):
		if len(self.provider.username) == 0:
			return False
		if self.settings['vip'] == '0':
			ret = client.getYesNoInput(self.session, xbmcutil.__lang__(30010))
			return ret
		return self.settings['vip'] == '1'

	def resolve(self, url):
		item = self.provider.video_item()
		item.update({'url':url})
		if not self.ask_for_account_type():
			# set user/pass to null - user does not want to use VIP at this time
			self.provider.username = None
			self.provider.password = None
		else:
			if not self.provider.login():
				client.showInfo(xbmcutil.__lang__(30011))
				return
		try:
			return self.provider.resolve(item, captcha_cb=self.ask_for_captcha)
		except ResolveException as e:
			self._handle_exc(e)




class XBMCLoginOptionalDelayedContentProvider(XBMCLoginOptionalContentProvider):

	def wait_cb(self, wait):
		left = wait
		msg = xbmcutil.__lang__(30014).encode('utf-8')
		while left > 0:
			#xbmc.executebuiltin("XBMC.Notification(%s,%s,1000,%s)" %(self.provider.name,msg % str(left),''))
			left -= 1
			time.sleep(1)

	def resolve(self, url):
		item = self.provider.video_item()
		item.update({'url':url})
		if not self.ask_for_account_type():
			# set user/pass to null - user does not want to use VIP at this time
			self.provider.username = None
			self.provider.password = None
		else:
			if not self.provider.login():
				client.showInfo(xbmcutil.__lang__(30011))
				return
		try:
			return self.provider.resolve(item, captcha_cb=self.ask_for_captcha, wait_cb=self.wait_cb)
		except ResolveException as e:
			self._handle_exc(e)

