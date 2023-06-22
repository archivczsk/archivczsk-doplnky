# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate
from tools_archivczsk.string_utils import _I, _C, _B

from .atk_loader import ATKClient
from .bouquet import AntikTVBouquetXmlEpgGenerator

from datetime import date, datetime, timedelta
import time
import base64

# #################################################################################################

class AntikTVModuleLiveTV(CPModuleLiveTV):
	def __init__(self, content_provider, channel_type):
		if channel_type == 'tv':
			name = content_provider._('Television')
			plot = content_provider._('Here you will find list of television channels')
		elif channel_type == 'radio':
			name = content_provider._('Radios')
			plot = content_provider._('Here you will find list of radio channels available with your subscription')
		elif channel_type == 'cam':
			name = content_provider._('Cameras')
			plot = content_provider._('Cameras from Kosice or other places in Slovakia')

		CPModuleLiveTV.__init__(self, content_provider, name, img=None, plot=plot, categories=(channel_type == 'tv'))
		self.channel_type = channel_type

	# #################################################################################################

	def get_live_tv_categories(self):
		self.add_live_tv_category(self.cp._("All"), None)
		for cat in self.cp.atk.get_categories(self.channel_type):
			self.add_live_tv_category(cat['name'], cat['id'])

	# #################################################################################################

	def get_live_tv_channels(self, cat_id=None):
		enable_adult = self.cp.get_setting('enable_adult')

		epg_list = [channel["id_content"] for channel in self.cp.atk.get_channels(self.channel_type, cat_id)]
		epg_list = self.cp.atk.get_actual_epg(epg_list)

		for channel in self.cp.atk.get_channels(self.channel_type, cat_id):
			if channel["adult"] and not enable_adult:
				continue

			try:
				epg = epg_list[ channel["id_content"] ]["epg"][0]

				if "subtitle" in epg:
					epg_str = "  " + _I(str(epg["title"]) + ": " + str(epg["subtitle"]))
					title = str(epg["title"]) + ": " + str(epg["subtitle"])
				else:
					epg_str = "  " + _I(epg["title"])
					title = str(epg["title"])

				time_prefix = self.cp.convert_time(epg["start"], epg["stop" ]) + "\n"
			except:
				epg = { "title": channel.get('desc_short', ''), "desc": channel.get('desc_long', '') }
				epg_str = "  " + _I(channel.get('desc_short', ''))
				title = str(channel.get('desc_short', ''))
				time_prefix = ""

			info_labels = {
				'plot': time_prefix + epg.get("desc", ""),
				'title': title
			}

			if not channel["adult"] or self.cp.pin_entered:
				img = channel.get("snapshot") or channel.get("logo").replace('.png', '_608x608.png')
			else:
				img = channel.get("logo").replace('.png', '_608x608.png')

			self.cp.add_video(channel["name"] + epg_str, img, info_labels=info_labels, download=False, cmd=self.resolve_play_url, channel_title=channel['name'], channel_id=channel['id'], epg_title=title, adult=channel['adult'])

	# #################################################################################################
	
	def resolve_play_url(self, channel_title, channel_id, epg_title, adult):
		if adult and not self.cp.pin_entered:
			answer = self.cp.get_text_input(self._('Please enter parental control pin'), input_type='pin')
			if answer == None:
				return
			elif not self.cp.check_pin(answer):
				self.cp.show_info(self._('Entered pin code is incorrect'), noexit=True)
				return

		url = self.channel_id_to_url(channel_id)
		self.cp.add_play(epg_title, url, info_labels={'title': channel_title}, settings=self.cp.player_settings)
	
	# #################################################################################################
	
	def channel_id_to_url(self, channel_id):
		key = '%s:%d' % (self.channel_type, channel_id)
		return self.cp.http_endpoint + '/playlive/' + base64.b64encode(key.encode('utf-8')).decode('utf-8')

# #################################################################################################

class AntikTVModuleArchive(CPModuleArchive):

	def __init__(self, content_provider):
		CPModuleArchive.__init__(self, content_provider)
		self.channel_type = 'tv'

	# #################################################################################################

	def root(self, archive_by=None):
		if archive_by == None:
			self.cp.add_dir(self._("By channels"), cmd=self.root, archive_by='channels')
			self.cp.add_dir(self._("By genres"), cmd=self.root, archive_by='genre')

		elif archive_by == 'channels':
			self.show_archive_channels()

		elif archive_by == 'genre':
			for genre in self.cp.atk.get_archive_genres():
				self.cp.add_dir(genre["title"], cmd=self.get_archive_genre, genre_id=genre["id"])

	# #################################################################################################

	def show_archive_channels(self):
		enable_adult = self.cp.get_setting('enable_adult')

		for channel in self.cp.atk.get_channels(self.channel_type):
			if channel["adult"] and not enable_adult:
				continue

			if channel["archive"]:
				self.add_archive_channel(channel['name'], channel["id"], 480, img=channel.get('logo').replace('.png', '_608x608.png'), show_archive_len=False)

	# #################################################################################################

	def convert_date(self, date_str, add_time=True):
		d = datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S")
		day_name = self.days_of_week[ d.weekday() ]

		response = "{:02d}.{:02d} ({})".format(d.day, d.month, day_name)

		if add_time == True:
			response = "{} {:02d}:{:02d}".format(response, d.hour, d.minute)

		return response

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		date_from, date_to = self.archive_day_to_datetime_range(archive_day)

		channel = self.cp.atk.get_channel_by_id(self.channel_type, channel_id)
		epg_list = self.cp.atk.get_channel_epg(channel['id_content'], date_from.isoformat() + "+0100", date_to.isoformat() + "+0100")

		for epg in epg_list:
			if epg.get("archived", False):
				# pridaj video
				epg_start = datetime.strptime(epg["start"][:19], "%Y-%m-%dT%H:%M:%S")
				epg_stop = datetime.strptime(epg["stop"][:19], "%Y-%m-%dT%H:%M:%S")
				title = "{:02}:{:02} - {:02d}:{:02d}".format(epg_start.hour, epg_start.minute, epg_stop.hour, epg_stop.minute)

				try:
					title = title + " - " + _I(epg["title"])
				except:
					pass

				info_labels = {
					'plot': epg.get("description"),
					'title': epg["title"],
					'genre': ', '.join(epg.get('genres', [])),
					'duration': epg['duration']
				}
				img = epg.get('image') if not channel['adult'] or self.cp.pin_entered else None
				self.cp.add_video(title, img, info_labels, cmd=self.get_archive_url, epg_title=str(epg["title"]), channel_id=channel['id_content'], epg_start=epg_start, epg_stop=epg_stop, adult=channel['adult'])

	# #################################################################################################

	def get_archive_genre(self, genre_id, offset=0):
		archives, count = self.cp.atk.get_archive_by_genre(self.cp.atk.get_archive_ids(), genre_id, 20, offset)
		return self.parse_archives(archives, count, offset, True, next_tag=self.get_archive_genre, genre_id=genre_id)

	# #################################################################################################

	def get_archive_serie(self, serie_id, offset=0):
		archives, count = self.cp.atk.get_archive_by_serie(self.cp.atk.get_archive_ids(), serie_id, 20, offset)
		return self.parse_archives(archives, count, offset, season_serie_id=serie_id, next_tag=self.get_archive_serie, serie_id=serie_id)

	# #################################################################################################

	def get_archive_season(self, serie_id, season_nr, offset=0):
		archives, count = self.cp.atk.get_archive_by_season(self.cp.atk.get_archive_ids(), serie_id, season_nr, 20, offset)
		return self.parse_archives(archives, count, offset, season_serie_id=serie_id, next_tag=self.get_archive_season, season_nr=season_nr)

	# #################################################################################################

	def parse_archives(self, archives, count, offset, simple_title=False, season_serie_id=None, next_tag=None, **next_tag_args):
		result = []

		for archive in archives:
			info_labels = {}
			img = None
			try:
				img = archive.get("icon")
				info_labels["rating"] = archive.get("score")

				if "type_series" in archive or "type_season" in archive:
					info_labels["plot"] = archive["description"]
				else:
					info_labels["plot"] = self.convert_date(archive["start"]) + " [" + str(archive["channel"]) + "]\n" + archive["description"]

			except:
				pass

			if "type_series" in archive:
				self.cp.add_dir(str(archive["title"]), img, info_labels, cmd=self.get_archive_serie, serie_id=archive["type_series"]["id"])
			elif "type_season" in archive:
				name = "Séria " + str(archive["type_season"]["season_number"])
				try:
					name = name + ": " + archive["title"]
				except:
					pass

				self.cp.add_dir(name, img, info_labels, cmd=self.get_archive_season, serie_id=season_serie_id, season_nr=archive["type_season"]["season_number"])
			else:
				# pridaj video
				if simple_title == True:
					try:
						title = archive["title"]
					except:
						title = self.convert_date(archive["start"])
				else:
					try:
						title = _I(archive["title"])
					except:
						title = self.convert_date(archive["start"])

					try:
						title = title + " [" + str(archive["channel"]) + "]"
					except:
						pass

				self.cp.add_video(title, img, info_labels, cmd=self.get_archive_url, epg_title=title, channel_id=archive["channel_id_content"], epg_start=archive["start"], epg_stop=archive["stop"])

		if count > offset + len(archives):
			self.cp.add_next(next_tag, offset=offset + len(archives), **next_tag_args)

	# #################################################################################################

	def get_archive_url(self, epg_title, channel_id, epg_start, epg_stop, adult=False):
		if adult and not self.cp.pin_entered:
			answer = self.cp.get_text_input(self._('Please enter parental control pin'), input_type='pin')
			if answer == None:
				return
			elif not self.cp.check_pin(answer):
				self.cp.show_info(self._('Entered pin code is incorrect'), noexit=True)
				return

		key = '%s$%s$%s$%s' % (self.channel_type, channel_id, epg_start, epg_stop)
		url = self.cp.http_endpoint + '/playarchive/' + base64.b64encode(key.encode('utf-8')).decode('utf-8')
		self.cp.add_play(epg_title, url, settings=self.cp.player_settings)

	# #################################################################################################

	def get_archive_hours(self, channel_id):
		return 480

	# #################################################################################################

	def get_channel_id_from_path(self, path):
		if path.startswith('playlive/'):
			channel_type, channel_id = self.cp.decode_playlive_url(path[9:])
			channel = self.cp.atk.get_channel_by_id(self.channel_type, int(channel_id))
			if channel['archive']:
				return int(channel_id)

		return None

# #################################################################################################

class AntikTVModuleExtra(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("Informations and settings"))

	# #################################################################################################

	def add(self):
		if self.cp.get_setting('enable_extra'):
			CPModuleTemplate.add(self)

	# #################################################################################################

	def root(self, section=None):
		if not self.cp.atk:
			return

		# Main menu
		self.cp.add_video(self._("User account"), cmd=self.account_info)
		self.cp.add_dir(self._("Purchased packages"), cmd=self.packages)
		self.cp.add_video(self._("Refresh channel list"), cmd=self.update_channels)
		self.cp.add_video(self._("Request device identification code"), cmd=self.get_device_support_id)
		self.cp.add_video(self._("Parental control PIN"), cmd=self.parental_pin, info_labels={'plot': self._('Default PIN is 0000. Please change it to your own value.')})
		self.cp.add_video(self._("Logout from this device"), cmd=self.logout)

	# #################################################################################################

	def update_channels(self):
		self.cp.atk.update_channels(force=True)
		self.cp.bxeg.bouquet_settings_changed("", "")
		self.cp.show_info(self._("Channel list was updated"), noexit=True)

	# #################################################################################################

	def get_device_support_id(self):
		did = self.cp.atk.get_device_support_id()
		self.cp.show_info(self._("Device identification code is: {did}").format(did=did), noexit=True)

	# #################################################################################################

	def parental_pin(self):
		answer = self.cp.get_text_input(self._('Please enter current parental control pin'), input_type='pin')
		if answer == None:
			return

		if not self.cp.check_pin(answer):
			self.cp.show_error(self._("Entered pin code is incorrect"), noexit=True)
			return

		answer = self.cp.get_text_input(self._('Please enter new parental control pin'), input_type='pin')
		if answer == None:
			return

		answer2 = self.cp.get_text_input(self._('Please repeat new parental control pin'), input_type='pin')
		if answer2 == None:
			return

		if answer != answer2:
			self.cp.show_error(self._("Parental control pins differs"), noexit=True)
			return

		self.cp.set_setting('pin', str(int(answer) * 8637 + 729))
		self.cp.pin_entered = False

		self.cp.show_info(self._("Parental control pin successfuly changed"), noexit=True)

	# #################################################################################################

	def packages(self):
		for x in self.cp.atk.get_active_packages():
			if x['from']:
				d = date.fromtimestamp(x['from']).strftime('%d.%m.%Y')
			else:
				d = '∞'

			d += ' - '
			if x['to']:
				d += date.fromtimestamp(x['to']).strftime('%d.%m.%Y')
			else:
				d += '∞'
				
			info_labels = {
				'plot': self._("To order more packages go to {antik_site}").format(antik_site='https://antiktv.sk')
			}
			self.cp.add_video(_I(x["name"]) + ': ' + d, info_labels=info_labels)

	# #################################################################################################
	
	def logout(self):
		answer = self.cp.get_yes_no_input(self.cp._("Do you really want to logout from this device?"))
		
		if answer:
			# reset username/password, because without that automatic login will be called again
			# and this is not what we want
			self.cp.atk.logout()
			self.cp.set_setting('username', "")
			self.cp.set_setting('password', "")
			self.cp.login_error(self.cp._("You have been logged out from this device"))

	# #################################################################################################

	def account_info(self):
		data = self.cp.atk.get_account_info()

		result = []
		result.append(self._("Customer") + ':')
		result.append(self._("Name") + ': ' + data["name"])
		result.append(self._("E-Mail") + ': ' + data["email"])
		result.append(self._("Customer key") + ": " + data["id"])
		result.append("")
		result.append(self._("This device identification") + ':')
		result.append(data['device_id'])
		result.append("")
		result.append(self._("Provider name") + ': ' + data['provider_name'])

		self.cp.show_info('\n'.join(result), noexit=True)

	# #################################################################################################

class AntikTVContentProvider(ModuleContentProvider):

	def __init__(self, settings, http_endpoint, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='AntikTV', settings=settings, data_dir=data_dir, bgservice=bgservice)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('username', 'password')

		self.atk = None

		self.http_endpoint = http_endpoint
		self.pin_entered = False

		# sometimes it's better to init modules at the end because variables the use are already initialised
		self.modules = [
			AntikTVModuleLiveTV(self, 'tv'),
			AntikTVModuleLiveTV(self, 'radio'),
			AntikTVModuleLiveTV(self, 'cam'),
			AntikTVModuleArchive(self),
			AntikTVModuleExtra(self)
		]
		self.add_initialised_callback(self.post_init)
		
	# #################################################################################################
	
	def do_ping(self):
		if self.atk.is_logged():
			self.log_debug("Calling PING")
			self.atk.ping()

	# #################################################################################################

	def post_init(self):
		self.player_settings = { 'user-agent': self.atk.user_agent }
		self.bxeg = AntikTVBouquetXmlEpgGenerator(self, self.http_endpoint, self.atk.user_agent)
		self.bgservice.run_in_loop("loop(ping)", (int(time.time()) % 900) + 1800, self.do_ping)

	# #################################################################################################

	def root(self):
		self.pin_entered = False
		ModuleContentProvider.root(self)

	# #################################################################################################
	
	def check_pin(self, answer, unlock=True):
		if len(answer) < 4:
			return False

		pin = int(self.get_setting('pin'))
		if pin == (int(answer) * 8637 + 729):
			if unlock:
				self.pin_entered = True
			return True

		return False

	# #################################################################################################
	# Provider init and configurations
	# #################################################################################################
	
	def convert_time(self, date_str, date2_str=None):
		d = datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S")
		response = "{:02d}:{:02d}".format(d.hour, d.minute)

		if date2_str != None:
			d = datetime.strptime(date2_str[:19], "%Y-%m-%dT%H:%M:%S")
			response += " - {:02d}:{:02d}".format(d.hour, d.minute)

		return response

	# #################################################################################################
	
	def login(self, silent):
		self.atk = ATKClient(self)
		self.atk.login()

		return True
	
	# #################################################################################################
	
	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		self.log_debug("Stats received: action=%s, duration=%s, position=%s" % (action, duration, position))

	# #################################################################################################

	def decode_playlive_url(self, url):
		return base64.b64decode(url.encode("utf-8")).decode("utf-8").split(':')

	# #################################################################################################

	def decode_playarchive_url(self, url):
		return base64.b64decode(url.encode("utf-8")).decode("utf-8").split('$')

# #################################################################################################

