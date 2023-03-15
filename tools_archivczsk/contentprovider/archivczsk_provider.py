# -*- coding: utf-8 -*-

import sys, os, re, traceback, time, json
from Plugins.Extensions.archivCZSK.engine import client
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from .exception import LoginException, AddonErrorException, AddonInfoException, AddonWarningException
from ..string_utils import _B

__addon__ = ArchivCZSK.get_addon('tools.archivczsk')


def _(id):
	return __addon__.get_localized_string(id)


def _icon(name):
	return os.path.join(__addon__.get_info('path'), 'resources', 'picture', name)

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
			self._save_searches(searches, server)
			
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
		searches = self._get_searches(server)
		
		if search in searches:
			searches.remove(search)
			
		searches.insert(0, search)
		self._cleanup_searches(server, searches, maximum, True)

	# #################################################################################################
	
	def remove_search(self, server, search):
		searches = self._get_searches(server)
		searches.remove(search)
		self._save_searches(searches, server)

	# #################################################################################################
	
	def edit_search(self, server, search, replacement):
		searches = self._get_searches(server)
		searches.remove(search)
		searches.insert(0, replacement)
		self._save_searches(searches, server)

	
# #################################################################################################

class ArchivCZSKContentProvider(object):
	"""
	Provider should not have direct dependency to archivczsk. Instead of it uses "dummy" functions.
	This is a interface, that "glues" archivczsk with provider based on CommmonContentProvider
	"""
	
	def __init__(self, provider, addon):
		self.provider = provider
		self.addon = addon
		self.addon_id = addon.id
		self.session = None
		self.searches = SearchProvider(addon, self.provider.name)
		self.__playlist = []
		self.login_refresh_running = False
		
		# set/overwrite interface methods for provider
		self.provider.add_dir = self.add_dir
		self.provider.add_search_dir = self.add_search_dir
		self.provider.add_next = self.add_next
		self.provider.add_video = self.add_video
		self.provider.add_play = self.add_play
		self.provider.add_playlist = self.add_playlist
		self.provider.add_menu_item = self.add_menu_item
		self.provider.show_info = self.show_info
		self.provider.show_error = self.show_error
		self.provider.show_warning = self.show_warning
		self.provider.get_yes_no_input = self.get_yes_no_input
		self.provider.get_list_input = self.get_list_input
		self.provider.get_text_input = self.get_text_input
		self.provider.refresh_screen = self.refresh_screen
		self.provider._ = addon.get_localized_string
		self.initialised_cbk_called = False
		self.login_tries = 0

		self.logged_in = self.process_login() # True = logged in, False = not logged, None = unknown

		if hasattr(self.provider, 'login_settings_names'):
			# if provider provided settings needed for login, then install notifier for autolog call
			self.addon.add_setting_change_notifier(self.provider.login_settings_names, self.login_data_changed)

		if hasattr(self.provider, 'login_optional_settings_names'):
			# if provider provided settings needed for login, then install notifier for autolog call
			self.addon.add_setting_change_notifier(self.provider.login_optional_settings_names, self.login_data_changed)

		if self.logged_in != None:
			self.call_initialised_cbk()
		else:
			# login ended with unknown login state, so do not call initialised callbacks - they need to know real login state (true/false)
			# plan login refresh in background
			self.log_info("Login status is unknown - planing delayed login in background")
			self.login_delayed()

	# #################################################################################################
	
	def log_debug(self, msg):
		client.log.debug('[%s] %s' % (self.provider.name, msg))

	def log_info(self, msg):
		client.log.info('[%s] %s' % (self.provider.name, msg))

	def log_error(self, msg):
		client.log.error('[%s] %s' % (self.provider.name, msg))

	# #################################################################################################

	def call_initialised_cbk(self):
		if self.initialised_cbk_called == False:
			try:
				self.initialised_cbk_called = True
				self.provider.initialised()
			except:
				self.log_error("Call of initalised callback failed:\n%s" % traceback.format_exc())

	# #################################################################################################

	def process_login(self, silent=True):
		if not hasattr(self.provider, 'login'):
			# provider has no login method - handle this as login OK
			return True

		if hasattr(self.provider, 'login_settings_names'):
			# provider has set setings needed for login - check if they are filled
			for name in self.provider.login_settings_names:
				value = self.addon.get_setting(name)
				if value == "":
					return False
		
		# check if we have correct time set - without correct time login process can fail
		if int(time.time()) < 1678802000:
			self.log_error("Time is not correct - returning unknown login state")
			return None

		# pre-checks passed - process real login
		logged_in = None
		
		try:
			logged_in = self.provider.login(silent)
		except LoginException as e:
			logged_in = False
			self.log_error("Login failed: %s" % str(e))

			if not silent:
				self.show_error(_('Login failed') + ':\n' + str(e), True)
		except Exception as e:
			self.log_error("Login ended with error: %s" % str(e))
			client.log.error(traceback.format_exc())

			if not silent:
				self.show_error(_('Login ended with error') + ':\n' + str(e), True)
		
		return logged_in

	# #################################################################################################

	def login_delayed(self):
		def __try_login():
			if self.logged_in != None:
				return

			if not self.login_refresh_running:
				self.log_debug("Trying new login in background")

				self.login_refresh_running = True

				self.logged_in = self.process_login()

				if self.logged_in == None:
					self.login_tries += 1

					if self.login_tries < 5:
						self.addon.bgservice.run_delayed('login_delayed(try login)', 30, None, __try_login)
					else:
						self.log_error("Background login failed: max retries reached")
				else:
					self.login_tries = 0
					self.log_info("Background login finished with status: %s" % str(self.logged_in))
					self.call_initialised_cbk()

				self.login_refresh_running = False
			else:
				self.log_debug("Background login already running")

		self.addon.bgservice.run_delayed('login_delayed(try login)', 10, None, __try_login)

	# #################################################################################################

	def login_data_changed(self, name, value):

		def __login_refreshed(success, result):
			if self.logged_in == True:
				self.log_debug("Login refreshed successfuly - user is logged in")
			elif self.logged_in == False:
				self.log_debug("Login refresh failed - user is not logged")
			else:
				self.log_debug("Login refresh failed - error occured during operation")

			self.login_refresh_running = False

		def __process_login_refresh():
			self.logged_in = self.process_login()
			self.call_initialised_cbk()

		if not self.login_refresh_running:
			self.log_debug("Login data changed - starting new login in background")
			self.login_refresh_running = True
			self.addon.bgservice.run_delayed('logindata_changed(refresh login)', 1, __login_refreshed, __process_login_refresh)
		else:
			self.log_debug("Background login already running")

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
					pl_name = pl_item['title']
				
				# create nice names for streams
				prefix = '[%d] ' % i
				
				for key in ('quality', 'bandwidth', 'vcodec', 'acodec', 'lang'):
					if key in pl_item['info_labels']:
						if key == 'bandwidth':
							if int(pl_item['info_labels'][key]) > 100:
								# filter out garbage
								prefix += '[%.1f MBit/s] ' % (float(pl_item['info_labels'][key]) / 1000000)
						else:
							prefix += '[%s] ' % pl_item['info_labels'][key]

				pl_item['info_labels']['title'] = pl_item['info_labels'].get('title', pl_item['title'])
				pl_item['title'] = prefix + pl_item['title']
				playlist.append(self.create_play_item(**pl_item))
				i += 1
			
			client.add_playlist(pl_name, playlist)

		self.__playlist = []
		
	# #################################################################################################

	def run(self, session, params, silent=False, allow_retry=True):
		self.session = session
		
		if self.logged_in != True:
			# this must be set to prevent calling login refresh when login config option changes during login phase
			# for example when during login new device id is generated
			self.login_refresh_running = True
			self.logged_in = self.process_login(silent)
			self.login_refresh_running = False

		if self.logged_in != None:
			# check if initialised callback was called and if not then call it
			self.call_initialised_cbk()

		if self.logged_in != True:
			return

		try:
			self.provider.silent_mode = silent

			if params == {}:
				self.provider.root()
			elif 'CP_action' in params:
				cp_action = params['CP_action']

				if callable(cp_action):
					cp_action(**params['CP_args'])
				else:
					# cp_action is not callable - probably shortcut, so handle this with care
					if hasattr(self.provider, "run_shortcut"):
						try:
							self.provider.run_shortcut(cp_action, params['CP_args'])
						except:
							self.log_error("Failed to run shortcut for action: %s\n%s" % (cp_action, traceback.format_exc()))

				self.__process_playlist()
		except LoginException as e:
			# login exception handler - try once more with new login
			self.logged_in = False
			if allow_retry:
				return self.run(session, params, silent, False)
			else:
				# login method returned True, but run returned LoginException
				client.showError(_('Login failed') + ': ' + str(e))

		except AddonErrorException as e:
			client.showError(str(e))

		except AddonInfoException as e:
			client.showInfo(str(e))

		except AddonWarningException as e:
			client.showWarning(str(e))

	# #################################################################################################

	def run_silent(self, session, params):
		self.run(session, params, silent=True)

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
	
	def search(self, session, keyword, search_id):
		self.do_search(search_id, keyword, False)

	# #################################################################################################

	def search_list(self, search_id=None, save_history=True):
		client.add_dir(_B(_('New search')), self.action(self.do_search, search_id=search_id, save_history=save_history), image=_icon('search.png'), search_item=True)
		
		try:
			maximum = int(self.provider.get_setting('keep-searches'))
		except:
			maximum = 10
		
		for what in self.searches.get_searches(search_id, maximum):
			menu_items = {
				_('Remove'): self.action(self.search_remove, search_id=search_id, what=what),
				_('Edit'): self.action(self.search_edit, search_id=search_id, what=what)
			}
			client.add_dir(what, self.action(self.do_search, search_id=search_id, what=what, save_history=save_history ), menuItems=menu_items )

	# #################################################################################################
	
	def search_remove(self, search_id=None, what=''):
		self.searches.remove_search(search_id, what)
		client.refresh_screen()

	# #################################################################################################
	
	def search_edit(self, search_id=None, what=''):
		replacement = client.getTextInput(self.session, _('Search'), what)

		if replacement != '':
			self.searches.edit_search(search_id, what, replacement)
			client.refresh_screen()

	# #################################################################################################
	
	def do_search(self, search_id=None, what='', save_history=True):
		if what == '':
			what = client.getTextInput(self.session, _('Search'))
			
		if not what == '':
			
			try:
				maximum = int(self.provider.get_setting('keep-searches'))
			except:
				maximum = 10

			if save_history:
				self.searches.add_search(search_id, what, maximum)
				
			self.provider.search(what, search_id)

	# #################################################################################################
	
	def add_menu_item(self, menu, title, cmd=None, **cmd_args):
		menu[title] = self.action(cmd, **cmd_args)
		
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
	
	def add_search_dir(self, title=None, search_id=None, img=None, info_labels={}, save_history=True):
		client.add_dir(title if title else _B(_('Search')), self.action(self.search_list, search_id=search_id, save_history=save_history), image=img if img else _icon('search.png'), search_folder=True)
		
	# #################################################################################################
	
	def add_next(self, cmd, **cmd_args):
		self.add_dir(_B(_('Next')), _icon('next.png'), cmd=cmd, **cmd_args)

	# #################################################################################################
	
	def _auto_play_video(self, title, urls, info_labels, data_item, trakt_item, download, **cmd_args):
		if not isinstance(urls, type([])):
			urls = [urls]
		
		for url in urls:
			if isinstance( url, type({}) ):
				info = {}
				for key in ('bandwidth', 'quality', 'vcodec', 'acodec', 'lang'):
					if key in url:
						info[key] = url[key]

				self.add_play(title, url['url'], info_labels=info, data_item=data_item, trakt_item=trakt_item, download=download, **cmd_args)
			else:
				self.add_play(title, url, info_labels=info_labels, data_item=data_item, trakt_item=trakt_item, download=download, **cmd_args)

	# #################################################################################################
	
	def create_video_item(self, title, img=None, info_labels={}, menu={}, data_item=None, trakt_item=None, download=True, cmd=None, **cmd_args):
		"""
		Actually the same as directory, but with different icon - should produce resolved video items using add_play()
		
		If cmd is callable, then it is called to produce resovled videos
		If cmd is dictionary, then it can hold informations about resolved video stream
		If cmd is string, then it holds direct url of resolved video
		More items can be passed as list (without callable type)
		"""
		if cmd == None or callable(cmd):
			item = client.create_directory_it(title, self.action(cmd, **cmd_args), image=img, infoLabels=info_labels, menuItems=menu, video_item=True, dataItem=data_item, traktItem=trakt_item, download=download)
		else:
			item = client.create_directory_it(title, self.action(self._auto_play_video, title=title, urls=cmd, info_labels=info_labels, data_item=data_item, trakt_item=trakt_item, download=download, **cmd_args), image=img, infoLabels=info_labels, menuItems=menu, video_item=True, dataItem=data_item, traktItem=trakt_item, download=download)

		return item

	def add_video(self, *args, **kwargs):
		item = self.create_video_item(*args, **kwargs)
		client.add_item(item)
	
	# #################################################################################################

	def create_play_item(self, title, url, info_labels={}, data_item=None, trakt_item=None, subs=None, settings=None, live=False, download=True):
		return client.create_video_it(name=title, url=url, subs=subs, infoLabels=info_labels, live=live, settings=settings, dataItem=data_item, traktItem=trakt_item, download=download)

	def add_play(self, title, url, info_labels={}, data_item=None, trakt_item=None, subs=None, settings=None, live=False, download=True, playlist_autogen=True):
		kwargs = {
			'title': title,
			'url': url,
			'info_labels': info_labels,
			'data_item': data_item,
			'trakt_item': trakt_item,
			'subs': subs,
			'settings': settings,
			'live': live,
			'download': download
		}

		if playlist_autogen:
			self.__playlist.append(kwargs)
		else:
			item = self.create_play_item(**kwargs)
			client.add_item(item)

	# #################################################################################################

	def add_playlist(self, title):
		class PlaylistInterface(object):
			def __init__(self, aczsk_provider, playlist):
				self.playlist = playlist
				self.aczsk_provider = aczsk_provider

			def add_play(self, *args, **kwargs):
				self.playlist.add(self.aczsk_provider.create_play_item(*args, **kwargs))

			def add_video(self, *args, **kwargs):
				self.playlist.add(self.aczsk_provider.create_video_item(*args, **kwargs))

		return PlaylistInterface(self, client.add_playlist(title))
		
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

	def get_text_input(self, title, text="", input_type="text"):
		'''
		input_type: text, number, pin (hidden numbers)
		'''
		if input_type == 'text':
			return client.getTextInput(self.session, title, text)
		elif input_type in ('number', 'pin'):
			return client.getNumericInput(self.session, title, text, showChars=(input_type == 'number'))
		else:
			# unknown input type
			return None

	# #################################################################################################
	
	def refresh_screen(self):
		client.refresh_screen()

	# #################################################################################################
