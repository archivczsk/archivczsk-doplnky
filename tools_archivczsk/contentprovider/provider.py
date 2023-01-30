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
import sys,os,re,traceback
from datetime import date, timedelta, datetime
import time
import json
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

	# #################################################################################################
	'''
	This method is called after full provider initialisation and after login was called. It can be used to
	start services or do wathever needed when login status is already known
	'''

	def initialised(self):
		return

	# #################################################################################################

	def __str__(self):
		return '[' + self.name +']'

	# #################################################################################################

	def _C(self, color, str):
		"""
		Returns colored text
		"""
		return '[COLOR %s]%s[/COLOR]' % (color, str)

	def _B(self, str):
		"""
		Returns bold text
		"""
		return '[B]%s[/B]' % str

	def _I(self, str):
		"""
		Returns italic text
		"""
		return '[I]%s[/I]' % str
	
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
		try:
			# standard addon interface
			self.settings.add_change_notifier(setting_names, cbk)
		except:
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
	
	def get_settings_checksum(self, names, extra=""):
		if not isinstance(names, (type(()), type([]))):
			names = [names]

		values = '|'.join(map(lambda name: str(self.get_setting(name)), names))
		values += extra
		return md5(values.encode('utf-8')).hexdigest()

	# #################################################################################################

	def login_error(self, msg=None):
		raise LoginException(msg)

	# #################################################################################################

	def login(self):
		"""
		This method should login customer or check if login is needed.
		A login method returns True on successfull login, False otherwise. It can also call login_error() to raise exception with message
		"""
		return True

	def search(self, keyword, search_id):
		"""
		Search for a keyword on a site
		Args:
					keyword (str)

		returns:
			array of video or directory items
		"""
		return
	
	def categories(self):
		"""
		Lists categories on provided site - this will generate root menu

		Returns:
			array of video or directory items
		"""
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

#	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		"""
		Used for playback statistics
		Args:
			item - set as data_item in video and dir
			action - play, watching, end, seek, pause, unpause
			duration - stream duration (if known)
			position - actual stream position (if known) 
			extra_params - extra params for future usage
		"""
	
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

	def add_play(self, title, url, info_labels={}, data_item=None, trakt_item=None, subs=None, settings=None, live=False):
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

	def get_yes_no_input(self, msg):
		# just dummy one
		return False

	def get_list_input(self, lst, title=""):
		# just dummy one
		return 0
				
# #################################################################################################

class LiveTVContentProvider(CommonContentProvider):
	# modules: live_tv, archive
	
	def __init__(self, name='dummy', settings=None, data_dir=None, bgservice=None, modules=None):
		CommonContentProvider.__init__(self, name, settings, data_dir, bgservice)
		self.days_of_week = ['Pondelok', 'Utorok', 'Streda', 'Štvrtok', 'Piatok', 'Sobota', 'Nedeľa']

		if modules:
			self.modules = modules
		else:
			# default used		
			self.modules = [
				( 'Live TV', 'live_tv', { 'categories': False } ),
				( 'Archív', 'archive', {} ),
			]

	# #################################################################################################
	
	def categories(self):
		for module_name, module_id, kwargs in self.modules:
			self.add_dir( module_name, cmd=getattr(self, 'module_' + module_id + '_root' ), **kwargs)

	# #################################################################################################
	
	def module_live_tv_root(self, categories=False, **kwargs):
		if categories:
			self.get_live_tv_categories(**kwargs)
		else:
			self.get_live_tv_channels(**kwargs)
	
	# #################################################################################################
	
	def module_archive_root(self, **kwargs):
		self.get_archive_channels(**kwargs)
	
	# #################################################################################################
	
	def add_live_tv_category(self, title, cat_id, img=None, info_labels={}):
		self.add_dir( title, img, info_labels, cmd=self.get_live_tv_channels, cat_id=cat_id)
	
	# #################################################################################################

	def add_archive_channel(self, title, channel_id, archive_hours, img=None, info_labels={}):
		self.add_dir( title, img, info_labels, cmd=self.get_archive_days_for_channels, channel_id=channel_id, archive_hours=archive_hours)
	
	# #################################################################################################

	def get_live_tv_categories(self):
		# implement this function if you want to support categories for Live TV
		# it should use add_live_tv_categoty() to add categories
		return
	
	# #################################################################################################
	
	def get_live_tv_channels(self, cat_id = None):
		# implement this function to get list of Live TV channels
		# it should call self.add_video() or self.add_play() to add videos or resolved videos
		return
	
	# #################################################################################################
	
	def get_archive_channels(self):
		# implement this function to get list of Live TV channels
		# it should call self.add_archive_channel()
		return
	
	# #################################################################################################

	def get_archive_days_for_channels(self, channel_id, archive_hours):
		# implement this function to get list days for channel_id
		# it should call self.add_archive_channel()
		
		for i in range(int(archive_hours//24)):
			if i == 0:
				day_name = "Dnes"
			elif i == 1:
				day_name = "Včera"
			else:
				day = date.today() - timedelta(days = i)
				day_name = self.days_of_week[day.weekday()] + " " + day.strftime("%d.%m.%Y")

			self.add_dir( day_name, cmd=self.get_archive_program, channel_id=channel_id, archive_day=i)
	
	# #################################################################################################
	
	def archive_day_to_datetime_range(self, archive_day, return_timestamp=False):
		"""
		Return datetime or timestamp range for archive day in form start, end
		"""
		
		if archive_day > 30:
			# archive day is in minutes
			from_datetime = datetime.now() - timedelta(minutes = archive_day) 
			to_datetime = datetime.now()
		elif archive_day == 0:
			from_datetime = datetime.combine(date.today(), datetime.min.time())
			to_datetime = datetime.now()
		else:
			from_datetime = datetime.combine(date.today(), datetime.min.time()) - timedelta(days = archive_day)
			to_datetime = datetime.combine(from_datetime, datetime.max.time())
		
		if return_timestamp:
			from_ts = int(time.mktime(from_datetime.timetuple()))
			to_ts = int(time.mktime(to_datetime.timetuple()))
			return from_ts, to_ts
		else:
			return from_datetime, to_datetime

	# #################################################################################################
	
	def get_archive_program(self, channel_id, archive_day):
		# implement this function to list program for channel_id and archive day (0=today, 1=yesterday, ...)
		# it should call self.add_archive_channel()
		return

	# #################################################################################################
	# Bouquet generator
	# #################################################################################################
	
