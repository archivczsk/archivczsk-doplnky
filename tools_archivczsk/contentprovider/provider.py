# -*- coding: utf-8 -*-

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
import sys, os, traceback

import json
import re
import requests
from datetime import datetime
from hashlib import md5
from .exception import LoginException

try:
	from Plugins.Extensions.archivCZSK.engine.client import log
except:
	# to make it run also without archivczsk
	class log:
		@staticmethod
		def debug(msg):
			pass

		@staticmethod
		def info(msg):
			pass

		@staticmethod
		def error(msg):
			pass


class DummyAddonBackgroundService(object):
	def __init__(self):
		pass

	@staticmethod
	def run_task(name, finish_cbk, fn, *args, **kwargs):
		pass

	@staticmethod
	def run_in_loop(name, seconds_to_loop, fn, *args, **kwargs):
		pass

	@staticmethod
	def run_delayed(name, delay_seconds, cbk, *args, **kwargs):
		pass

# #################################################################################################

class CommonContentProvider(object):
	"""
	CommonContentProvider class provides an internet content. It should NOT have any archivczsk imports
	and must be testable without archivczsk runtime. This is a basic implementation. You should
	create your own implementation on top of this class.
	"""

	def __init__(self, name='dummy', settings=None, data_dir=None, bgservice=None):
		self.name = name
		self.settings = settings
		self.bgservice = bgservice if bgservice != None else DummyAddonBackgroundService()
		self.data_dir = data_dir if data_dir else '/tmp'
		self.__initialised_cbks = []

		# if silent_mode is set to True, then addon should not perform any user interaction and should do all work silently
		self.silent_mode = False

		# If you set this property, then values of those settings names will be checked, if they are filled.
		# If not, then login process will end as not logged and no login() method will be called. If some of those
		# settings changes, then new login procedure will be automaticaly called.
#		self.login_settings_names = ('username', 'password')

		# Here you can set some optional settings. They don't need to be filled, but when they change,
		# then new login procedure will be automaticaly called.
#		self.login_optional_settings_names = ('pin')

	# #################################################################################################

	def _(self, s):
		'''
		Returns localised string if localisations service is available
		'''
		return s

	# #################################################################################################

	def __str__(self):
		return '[' + self.name + ']'

	# #################################################################################################

	def initialised(self):
		'''
		This method is called after full provider initialisation and after login was called. It can be used to
		start services or do wathever needed when login status is already known
		Don't override this function - add own callback with add_initialised_callback() if you need this functionality
		'''
		for cbk, args, kwargs in self.__initialised_cbks:
			cbk(*args, **kwargs)

	# #################################################################################################

	def run_shortcut(self, action, kwargs):
		'''
		Tries to run shortcut created by engine. Engine simply serialises all data in params to strings, so when it finds
		pointer to function it runs str() on it and serialises its data. The same will happen with all action arguments.
		This function parses string with action name, tries to check, if action should be run on instance of this provider
		and if everything passes, then it will search for right method and will run it. Everything here is not safe and it's
		more or less a hack. Not all shortcuts will work, but when only method is callable and all other arguments are serializable,
		then it should work.
		'''
		self.log_info("Trying to run shortcut: %s" % action)
		qualname = None

		if action.startswith('<bound method '):
			qualname = action.split(' ')[2]
			modulename = action.split(' ')[4][1:]

		if not qualname or not modulename:
			self.log_debug("Can't get qualname of action - givig up")
			return

		self.log_debug("Full qualname of action: %s" % qualname)
		self.log_debug("Full module name of action: %s" % modulename)

		# extract class name and method
		modulename, class_name = modulename.rsplit('.', 1)
		method = qualname.split('.')[1]

		# check if class is child of this provider
		if not isinstance(self, getattr(sys.modules[modulename], class_name)):
			self.log_error("Class name %s is not child of %s - giving up" % (class_name, self.__class__.__name__))
			return

		# run the action
		getattr(self, method)(**eval(kwargs))

	# #################################################################################################
	# In your own content provider you should implement these functions (based on functionality)
	# at least root() function needs to be implemented, because without it your provider will do nothing :-)
	# #################################################################################################

	def login(self, silent):
		"""
		This method should login customer or check if login is needed. If silent is True, then only silent login without user interaction is allowed.
		If you set variable self.login_settings_names, then those settings will be checked, if they are filled before calling this method.
		A login method returns True on successfull login, False otherwise. It can also call login_error() to raise exception with message
		"""
		return True

	def search(self, keyword, search_id):
		"""
		Search for a keyword. search_id is used to distinguish between multiple search types (eg. movie, artist, ...)
		"""
		return

	def root(self):
		""" Lists/generates root menu - this is entry point for the user """
		return

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		"""
		Used to collect playback statistics or react on events from player
		Args:
			item - set as data_item in video and dir
			action - play, watching, end, seek, pause, unpause
			duration - stream duration (if known)
			position - actual stream position (if known)
			extra_params - extra params for future usage
		"""
		return

#	def trakt(self, trakt_item, action, result):
		"""
		Addon must have setting (bool) trakt_enabled ... and must be enabled to show trakt menu
		and must set 'trakt_item' key with 'ids' dictionary with imdb, tvdb, trakt keys (identify video item in trakt.tv) to dir or video item
		trakt actions are handled directly by archivCZSK core - this callback is used as notification
		to perform aditional operations related directly to addon

		Possible actions:
			- add		add item to watchlist
			- remove	remove item from watchlist
			- watched	add to watched collection
			- unwatched remove from watched collection
			- scrobble  automatic scrobble (add to watched) when >80% of movie was watched
			- reload    reload local cache

		result - result of operation from core as dictionary { 'success': True/False, 'msg': 'description of result' }
		"""

	# #################################################################################################
	# Here is API that you can use to communicate with engine or do everything needed to provide content
	# that will be displayed to user
	# #################################################################################################

	def add_initialised_callback(self, cbk, *args, **kwargs):
		'''
		Adds callback function that should be called after initialisation is finished
		'''
		self.__initialised_cbks.append((cbk, args, kwargs))

	# #################################################################################################

	def get_setting(self, name):
		"""
		Returns value of a setting with name
		"""
		try:
			# standard addon interface
			return self.settings.get_setting(name)
		except:
			# fallback
			if isinstance( self.settings, type({}) ):
				return self.settings.get(name)
			elif callable(self.settings):
				return self.settings(name)

		return None

	# #################################################################################################

	def set_setting(self, name, value):
		"""
		Sets value of a setting with name
		"""
		try:
			# standard addon interface
			self.settings.set_setting(name, value)
		except:
			# fallback
			if isinstance( self.settings, type({}) ):
				self.settings[name] = value

	# #################################################################################################

	def add_setting_change_notifier(self, setting_names, cbk):
		self.log_debug("Adding change notifier for settings: %s" % str(setting_names))
		try:
			# standard addon interface
			self.settings.add_change_notifier(setting_names, cbk)
		except:
			self.log_exception()
			# fallback
			pass

	# #################################################################################################

	def load_cached_data(self, name):
		ret = {}
		try:
			with open(os.path.join(self.data_dir, name + '.json'), "r") as f:
				ret = json.load(f)
		except:
			pass

		return ret

	# #################################################################################################

	def save_cached_data(self, name, data):
		try:
			with open(os.path.join(self.data_dir, name + '.json'), "w") as f:
				json.dump(data, f)
		except:
			self.log_error(traceback.format_exc())
			pass

	# #################################################################################################

	def update_cached_data(self, name, data):
		data_loaded = self.load_cached_data(name)
		data_loaded.update(data)
		self.save_cached_data(name, data_loaded)

	# #################################################################################################

	def get_settings_checksum(self, names, extra=None):
		'''
		Creates checksum of values of settings with provided names + extra parameter. It is usefull when one needs to chceck if cached data (like session, access token, ...) was created
		with settings that are already set.
		'''
		if not isinstance(names, (type(()), type([]))):
			names = [names]

		values = '|'.join(map(lambda name: str(self.get_setting(name)), names))
		if extra:
			values += extra
		return md5(values.encode('utf-8')).hexdigest()

	# #################################################################################################

	def login_error(self, msg=None):
		'''
		Raises login exception that will produce automatic re-login attempt (or will show message, if login fails).
		'''
		raise LoginException(msg)

	# #################################################################################################

	def get_hls_streams(self, url, requests_session=None, headers=None, max_bitrate=None):
		'''
		Returns streams from hls master playlist. Only EXT-X-STREAM-INF addresses are returned.
		If master playlist contains EXT-X-MEDIA tags, then returned streams are not directly playable and HlsHTTPRequestHandler needs to be used to convert master playlist to right format.
		url - url of master playslist
		requests_session - session to use
		headers - additional requests headers (if needed)
		max_bitrate - max bitrate in Mbits/s of returned streams

		returns list of stream informations sorted by bitrate (from max)
		'''
		try:
			if requests_session:
				response = requests_session.get(url, headers=headers)
			else:
				response = requests.get(url, headers=headers)
		except:
			self.log_exception()
			return None

		if response.status_code != 200:
			self.log_error("Status code response for HLS master playlist: %d" % response.status_code)
			return None

		if max_bitrate and int(max_bitrate) > 0:
			max_bitrate = int(max_bitrate) * 1000000
		else:
			max_bitrate = 1000000000

		streams = []

		for m in re.finditer(r'^#EXT-X-STREAM-INF:(?P<info>.+)\n(?P<chunk>.+)', response.text, re.MULTILINE):
			stream_info = {}
			for info in re.split(r''',(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''', m.group('info')):
				key, val = info.split('=', 1)
				stream_info[key.strip().lower()] = val.strip()

			stream_url = m.group('chunk')

			if not stream_url.startswith('http'):
				if stream_url.startswith('/'):
					stream_url = url[:url[9:].find('/') + 9] + stream_url
				else:
					stream_url = url[:url.rfind('/') + 1] + stream_url

			stream_info['url'] = stream_url
			if int(stream_info.get('bandwidth', 0)) <= max_bitrate:
				streams.append(stream_info)

		return sorted(streams, key=lambda i: int(i['bandwidth']), reverse=True)

	# #################################################################################################
	@staticmethod
	def timestamp_to_str(ts, format='%H:%M'):
		return datetime.fromtimestamp(ts).strftime(format)

	# #################################################################################################

	def show_error(self, msg, noexit=False, timeout=0):
		if noexit:
			self.log_error(msg)
		else:
			raise Exception('[ERROR] ' + msg)

	def show_warning(self, msg, noexit=False, timeout=0):
		if noexit:
			self.log_warning(msg)
		else:
			raise Exception('[WARNING] ' + msg)

	def show_info(self, msg, noexit=False, timeout=0):
		if noexit:
			self.log_info(msg)
		else:
			raise Exception('[INFO] ' + msg)

	def log_debug(self, msg):
		log.debug('[%s] %s' % (self.name, msg))

	def log_info(self, msg):
		log.info('[%s] %s' % (self.name, msg))

	def log_error(self, msg):
		log.error('[%s] %s' % (self.name, msg))

	def log_exception(self):
		log.error('[%s] Exception caught:\n%s' % (self.name, traceback.format_exc()))

	def add_dir(self, title, img=None, info_labels={}, menu={}, data_item=None, trakt_item=None, cmd=None, **cmd_args):
		"""
		info_labels = {
			'plot': 'Obsah, popis',
			'genre': 'Zaner',
			'rating': 'Hodnotenie', # float
			'year': 'Rok ako int',
			'duration': 'Dlzka v sekundach ako int',
			'adult': "True if it's an adult content'
		}
		"""
		pass

	def add_next(self, cmd, page_info=None, **cmd_args):
		'''
		Adds shortcut to next page
		'''
		pass

	def add_search_dir(self, title=None, search_id='', img=None, info_labels={}):
		"""
		info_labels = {
			'plot': 'Obsah, popis',
			'genre': 'Zaner',
			'rating': 'Hodnotenie', # float
			'year': 'Rok ako int',
			'duration': 'Dlzka v sekundach ako int'
		}
		"""
		pass

	def add_video(self, title, img=None, info_labels={}, menu={}, data_item=None, trakt_item=None, download=True, cmd=None, **cmd_args):
		"""
		Not yet resolved video - should produce resolved video items using add_play()
		"""
		pass

	def add_play(self, title, url, info_labels={}, data_item=None, trakt_item=None, subs=None, settings=None, live=False, download=True, playlist_autogen=True):
		"""
		Set resolved stream, that can be played by player.
		info_labels - stream info labels
		{
			'quality'
			'bandwidth'
			'vcodec'
			'acodec'
			'lang'
		}

		settings - dictionary with settings for player:
		{
			'resume_time_sec': resume time
			'user-agent': user agent to use by player
			'extra-headers': aditional extra HTTP headers
			'forced_player': service reference used for player (4097, 5001, 5001, ...)
			'lang_priority': list of priority langs used for audio and subtitles - audio will be automatically switched to first available language
			'lang_fallback': list of fallback langs - audio will be automatically switched to first available language, but also subtitles will be enabled
			'subs_autostart': allow autostart of subtitles (when subtitle lang will be found in lang_priority)
			'subs_always': always start subtitles, even if audio from lang_priority was found
			'subs_forced_autostart': start subtitles when forced subtitle track is found (this is poorly supported by enigma)
		}
		"""
		pass

	def add_playlist(self, title, variant=False):
		"""
		Adds new playlist to content screen and returns interface to add items to it (using add_video and add_play methods)
		variant - defines variant playlist - playlist contains the same video content with various qualities
		"""
		# just fake interface here
		return self

	def sort_content_items(self, reverse=False, use_diacritics=True, ignore_case=False):
		"""
		Sort content items added with add_dir/add_video/add_play/add_playlist
		"""
		return

	def create_ctx_menu(self):
		"""
		Creates context menu and returns interface to create items using add_menu_item() and add_media_menu_item()
		"""
		return self

	def add_menu_item(self, menu, title, cmd=None, **cmd_args):
		'''
		Used to add item to context menu.
		'''
		pass

	def add_media_menu_item(self, menu, title, cmd=None, **cmd_args):
		'''
		Used to add media item to context menu. Media item is used to directly play video from context menu (should produce video files).
		'''
		pass

	def get_yes_no_input(self, msg):
		'''
		Asks user a yes/no question
		'''
		# just dummy one
		return False

	def get_list_input(self, lst, title=""):
		'''
		Asks user to choose from list items. It returns index of selected item or None if user hits cancel.
		'''
		# just dummy one
		return 0

	def get_text_input(self, title, text="", input_type="text"):
		'''
		Asks user to enter some text. Response is always returned as text or None if user hits cancel.
		title - Title to show in input dialog
		text - prefilled text
		input_type: type of input box to show. Allowed types are: text (standard virtual keyboard), number (input box for numbers), pin (the same as number, but hidden)
		'''
		return ""

	def refresh_screen(self):
		'''
		Refreshes/reloads the actual screen. Usefull when something changes on actual screen.
		'''
		return

	def get_lang_code(self):
		'''
		Returns current used language code for GUI
		'''
		# just dummy one
		return 'en'

	def youtube_resolve(self, url):
		'''
		Resolves youtube link to video streams using youtube_dl
		'''
		return None

	def get_addon_version(self):
		'''
		Returns addon's version
		'''
		return '1.0'

	def get_engine_version(self):
		'''
		Returns enigne's version (version of ArchivCZSK)
		'''
		return '2.2.0'

	def get_profile_name(self):
		'''
		Returns name of current addon virtual profile or empty string if running in main profile
		'''
		return ''

	def get_parental_settings(self, name=None):
		'''
		Returns current parental control configuration
		'''
		s = {
			'unlocked': True,
			'show_adult': True,
			'show_posters': True
		}

		if name != None:
			return s.get(name)
		else:
			return s
