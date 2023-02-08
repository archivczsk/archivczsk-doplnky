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
import os, traceback

import json
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
	def run_task(finish_cbk, fn, *args, **kwargs):
		pass

	@staticmethod
	def run_in_loop(seconds_to_loop, fn, *args, **kwargs):
		pass

	@staticmethod
	def run_delayed(delay_seconds, cbk, *args, **kwargs):
		pass
		
# #################################################################################################

class CommonContentProvider(object):
	"""
	ContentProvider class provides an internet content. It should NOT have any xbmc-related imports
	and must be testable without XBMC runtime. This is a basic/dummy implementation.
	"""

	def __init__(self, name='dummy', settings=None, data_dir=None, bgservice=None):
		self.name = name
		self.settings = settings
		self.bgservice = bgservice if bgservice != None else DummyAddonBackgroundService()
		self.data_dir = data_dir if data_dir else '/tmp'
		self.__initialised_cbks = []

	# #################################################################################################
	'''
	This method is called after full provider initialisation and after login was called. It can be used to
	start services or do wathever needed when login status is already known
	If you override this function, then don't forget to call it from child class also, so that
	__initialised_cbks gets called.
	'''

	def initialised(self):
		for cbk, args, kwargs in self.__initialised_cbks:
			cbk(*args, **kwargs)

	# #################################################################################################

	def add_initialised_callback(self, cbk, *args, **kwargs):
		'''
		Adds callback function that should be called after initialisation is finished
		'''
		self.__initialised_cbks.append((cbk, args, kwargs))

	# #################################################################################################

	def __str__(self):
		return '[' + self.name +']'

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
		if not isinstance(names, (type(()), type([]))):
			names = [names]

		values = '|'.join(map(lambda name: str(self.get_setting(name)), names))
		if extra:
			values += extra
		return md5(values.encode('utf-8')).hexdigest()

	# #################################################################################################

	def login_error(self, msg=None):
		raise LoginException(msg)

	# #################################################################################################
	@staticmethod
	def timestamp_to_str(ts, format='%H:%M'):
		return datetime.fromtimestamp(ts).strftime(format)

	# #################################################################################################

	def login(self):
		"""
		This method should login customer or check if login is needed.
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
	
	def show_error(self, msg, noexit=False, timeout=0, can_close=True ):
		if noexit:
			self.log_error(msg)
		else:
			raise Exception('[ERROR] ' + msg)

	def show_warning(self, msg, noexit=False, timeout=0, can_close=True):
		if noexit:
			self.log_warning(msg)
		else:
			raise Exception('[WARNING] ' + msg)

	def show_info(self, msg, noexit=False, timeout=0, can_close=True):
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

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		"""
		Used for playback statistics
		
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
		pass

	def add_next(self, cmd, **cmd_args):
		pass

	def add_search_dir(self, title, search_id='', img=None, info_labels={}):
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

	def add_video(self, title, img=None, info_labels={}, menu={}, data_item=None, trakt_item=None, cmd=None, **cmd_args):
		"""
		Not yet resolved video - should produce resolved video items using add_resolved_video_item()
		"""
		pass

	def add_play(self, title, url, info_labels={}, data_item=None, trakt_item=None, subs=None, settings=None, live=False, playlist_autogen=True):
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
			'process_hls_master' : True/False - Enable disable of processing hls mater playlist and extracting streams from it
			'forced_player': service reference used for player (4097, 5001, 5001, ...)
		}
		"""
		pass

	def add_menu_item(self, menu, title, cmd=None, **cmd_args):
		pass

	def get_yes_no_input(self, msg):
		# just dummy one
		return False

	def get_list_input(self, lst, title=""):
		# just dummy one
		return 0

	def refresh_screen(self):
		return
