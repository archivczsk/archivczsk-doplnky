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

import sys, os, re, traceback, time
from Plugins.Extensions.archivCZSK.engine import client
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

__addon__ = ArchivCZSK.get_addon('tools.archivczsk')

def _tr(id):
	return __addon__.get_localized_string(id)


def _icon(name):
	return 'https://github.com/lzoubek/xbmc-doplnky/raw/dharma/icons/' + name

# #################################################################################################

class SearchProvider(object):
	def __init__(self, addon, name):
		self.data_dir = addon.get_info('profile')
		self.name = name
	
	# #################################################################################################
	
	def _get_searches(self, server):
		if server == None:
			server = ''
		local = os.path.join(self.data_dir, self.name + server)

		try:
			with open(local, 'r') as f:
				searches = json.load(f)
		except:
			searches = []
		
		return searches
	
	# #################################################################################################
	
	def _cleanup_searches(self, server, searches, maximum=10, force_save=False):
		remove = len(searches) - maximum
		if remove > 0:
			for i in range(remove):
				searches.pop()
		
		if remove > 0 or force_save:
			_self.save_searches(searches, server)
			
		return searches
	
	# #################################################################################################
	
	def _save_searches(self, searches, server):
		if server == None:
			server = ''

		local = os.path.join(self.data_dir, self.name + server)
		
		with open(local, 'w') as f:
			json.dump(searches, f)
			
	# #################################################################################################
	
	def get_searches(self, server, maximum=10):
		searches = self._get_searches(server)
		return self._cleanup_searches(server, searches, maximum)
	
	# #################################################################################################
	
	def add_search(self, server, search, maximum=10):
		searches = self._get_searchers(server, maximum)
		
		if search in searches:
			searches.remove(search)
			
		searches.insert(0, search)
		self._cleanup_searches(server, searches, maximum, True)

	# #################################################################################################
	
	def remove_search(self, server, search):
		searches = self._get_searchers(server)
		searches.remove(search)
		self._save_searches(searches, server)

	# #################################################################################################
	
	def edit_search(self, server, search, replacement):
		searches = self._get_searchers(server)
		searches.remove(search)
		searches.insert(0, replacement)
		self._save_searches(searches, server)

	
# #################################################################################################

class ArchivCZSKContentProvider(object):
	"""
	Provider should not have direct dependency to archivczsk. Instead of it uses "dummy" functions.
	This is a interface, that "glues" archivczsk with provider
	"""
	
	def __init__(self, provider, addon):
		self.provider = provider
		self.addon = addon
		self.addon_id = addon.id
		self.session = None
		self.search = SearchProvider(addon, self.provider.name)
		self.__playlist = []
		self.playlist_autogen = True
		
		# set/overwrite interface methods for provider
		self.provider.add_dir = self.add_dir
		self.provider.add_search_dir = self.add_search_dir
		self.provider.add_next = self.add_next
		self.provider.add_video = self.add_video
		self.provider.add_play = self.add_play
		self.provider.show_info = self.show_info
		self.provider.show_error = self.show_error
		self.provider.show_warning = self.show_warning
		self.provider.get_yes_no_input = self.get_yes_no_input
		self.provider.get_list_input = self.get_list_input

	# #################################################################################################
	
	def action(self, cmd, **cmd_args ):
		return {
			'CP_action': cmd if cmd else lambda *args: None,
			'CP_args': cmd_args
		}
	
	# #################################################################################################
	
	def __process_playlist(self):
		# check if there are som playable items in playlist			
		if len( self.__playlist ) == 1:
			# only one item - create one normal video item
			client.add_video(**self.__playlist[0])
		elif len( self.__playlist ) > 1:
			# we have more streams - create playlist and play the first one
			playlist = []
			
			pl_name = None
			i = 1
			for pl_item in self.__playlist:
				if not pl_name:
					pl_name = pl_item['name']
				
				# create nice names for streams
				prefix = '[%d] ' % i
				
				for key in ('quality', 'vcodec', 'acodec', 'lang'):
					if key in pl_item['infoLabels']:
						prefix += '[%s] ' % pl_item['infoLabels'][key] 
				
				pl_item['name'] = prefix + pl_item['name']
				playlist.append(client.create_video_it(**pl_item))
				i += 1
			
			client.add_playlist(pl_name, playlist)

		self.__playlist = []
		
	# #################################################################################################

	def run(self, session, params):
		self.session = session
		
		if params == {}:
			if hasattr(self.provider, 'login') and not self.provider.login():
				client.showInfo(_tr(30011))
				return
			
			self.provider.categories()
		elif 'CP_action' in params:
			params['CP_action'](**params['CP_args'])
			self.__process_playlist()

	# #################################################################################################
	
	def trakt(self, session, item, action, result ):
		if hasattr(self.provider, 'trakt'):
			self.session = session
			self.provider.trakt(item, action, result)
		
	# #################################################################################################
	
	def stats(self, session, item, action, **extra_params ):
		if hasattr(self.provider, 'stats'):
			self.session = session
			self.provider.stats(item, action, **extra_params)
	
	# #################################################################################################
	
	def search_list(self, search_id=None, save_history=True):
		client.add_dir(_tr(30004), self.action(self.do_search, search_id=search_id, save_history=save_history), image=_icon('search.png'), search_item=True)
		
		try:
			maximum = int(self.provider.get_setting('keep-searches'))
		except:
			maximum = 10
		
		for what in self.searches.get_searches(search_id, maximum):
			menu_items = {
				u'Remove': self.action(self.search_remove, search_id=search_id, what=what),
				u'Edit': self.action(self.search_edit, search_id=search_id, what=what)
			}
			client.add_dir(what, self.action(self.do_search, search_id=search_id, what=what, save_history=save_history ), menuItems=menu_items )

	# #################################################################################################
	
	def search_remove(self, search_id=None, what=''):
		self.searches.remove_search(search_id, what)
		client.refresh_screen()

	# #################################################################################################
	
	def search_edit(self, search_id=None, what=''):
		replacement = client.getTextInput(self.session, _tr(30003), what)

		if replacement != '':
			self.searches.edit_search(search_id, what, replacement)
			client.refresh_screen()

	# #################################################################################################
	
	def do_search(self, search_id=None, what='', save_history=True):
		if what == '':
			what = client.getTextInput(self.session, _tr(30003))
			
		if not what == '':
			
			try:
				maximum = int(self.provider.get_setting('keep-searches'))
			except:
				maximum = 10

			if save_history:
				self.search.add_search(search_id, what, maximum)
				
			self.provider.search(what, search_id)

	# #################################################################################################
	
	def add_dir(self, title, img=None, info_labels={}, menu={}, data_item=None, trakt_item=None, cmd=None, **cmd_args):
		"""
		info_labels = {
			'plot': 'Obsah, popis',
			'genre': 'Zaner',
			'rating': 'Hodnotenie', # float
			'year': 'Rok ako int',
			'duration': 'Dlzka v sekundach ako int'
		}
		"""
		client.add_dir(title, self.action(cmd, **cmd_args), image=img, infoLabels=info_labels, menuItems=menu, video_item=False, dataItem=data_item, traktItem=trakt_item)
		
	# #################################################################################################
	
	def add_search_dir(self, title, search_id=None, img=None, info_labels={}, save_history=True ):
		client.add_dir(title, self.action(self.search_list, search_id=search_id, save_history=save_history), image=img if img else _icon('search.png'), search_folder=True)
		
	# #################################################################################################
	
	def add_next(self, cmd, **cmd_args):
		self.add_dir(_tr(30007), _icon('next.png'), cmd=cmd, **cmd_args)

	# #################################################################################################
	
	def __auto_play_video(self, title, urls, info_labels, data_item, trakt_item, **cmd_args ):
		if not isinstance(urls, type([])):
			urls = [urls]
		
		for url in urls:
			if isinstance( url, type({}) ):
				info = {}
				for key in ('bandwidth', 'quality', 'vcodec', 'acodec', 'lang'):
					if key in url:
						info[key] = url[key]

				self.add_play(title, url['url'], info_labels=info, data_item=data_item, trakt_item=trakt_item, **cmd_args)
			else:
				self.add_play(title, url, info_labels=info_labels, data_item=data_item, trakt_item=trakt_item, **cmd_args)

	# #################################################################################################
	
	def add_video(self, title, img=None, info_labels={}, menu={}, data_item=None, trakt_item=None, cmd=None, **cmd_args):
		"""
		Actually the same as directory, but with different icon - should produce resolved video items using add_play()
		
		If cmd is callable, then it is called to produce resovled videos
		If cmd is dictionary, then it can hold informations about resolved video stream
		If cmd is string, then it holds direct url of resolved video
		More items can be passed as list (without callable type)
		"""
		if cmd == None or callable(cmd):
			client.add_dir(title, self.action(cmd, **cmd_args), image=img, infoLabels=info_labels, menuItems=menu, video_item=True, dataItem=data_item, traktItem=trakt_item)
		else:
			client.add_dir(title, self.action(self.__auto_play_video, title=title, urls=cmd, info_labels=info_labels, data_item=data_item, trakt_item=trakt_item, **cmd_args), image=img, infoLabels=info_labels, menuItems=menu, video_item=True, dataItem=data_item, traktItem=trakt_item)
	
	# #################################################################################################
	
	def add_play(self, title, url, info_labels={}, data_item=None, trakt_item=None, subs=None, settings=None, live=False):
		def __add_play(**kwargs):
			if self.playlist_autogen:
				self.__playlist.append(kwargs)
			else:
				client.add_video(**kwargs)
		
		__add_play(name=title, url=url, subs=subs, infoLabels=info_labels, live=live, settings=settings, dataItem=data_item, traktItem=trakt_item)
				
	# #################################################################################################
	
	def show_error(self, msg, noexit=False, timeout=0, can_close=True ):
		if noexit:
			client.add_operation('SHOW_MSG', { 'msg': msg, 'msgType': 'error', 'msgTimeout': timeout, 'canClose': can_close, })
		else:
			client.showError(msg)

	# #################################################################################################
	
	def show_warning(self, msg, noexit=False, timeout=0, can_close=True ):
		if noexit:
			client.add_operation('SHOW_MSG', { 'msg': msg, 'msgType': 'warning', 'msgTimeout': timeout, 'canClose': can_close, })
		else:
			client.showWarning(msg)

	# #################################################################################################
	
	def show_info(self, msg, noexit=False, timeout=0, can_close=True ):
		if noexit:
			client.add_operation('SHOW_MSG', { 'msg': msg, 'msgType': 'info', 'msgTimeout': timeout, 'canClose': can_close, })
		else:
			client.showInfo(msg)
		
	# #################################################################################################
	
	def get_yes_no_input(self, msg):
		return client.getYesNoInput(self.session, msg)

	# #################################################################################################

	def get_list_input(self, lst, title=""):
		return client.getListInput(self.session, lst, title)

	# #################################################################################################
	
