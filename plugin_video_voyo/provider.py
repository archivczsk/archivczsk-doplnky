# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.string_utils import _I, _C, _B, int_to_roman
from tools_archivczsk.cache import SimpleAutokeyExpiringCache
from tools_archivczsk.player.features import PlayerFeatures
from .voyo import Voyo
from functools import partial

class VoyoContentProvider(CommonContentProvider):

	def __init__(self):
		CommonContentProvider.__init__(self, 'Voyo')
		self.voyo = None
		self.login_optional_settings_names = ('login_type', 'username', 'password')
		self.scache = SimpleAutokeyExpiringCache()
		self.favorites = {}

	# ##################################################################################################################

	def login(self, silent):
		if not self.get_setting('username') or not self.get_setting('password'):
			if not silent:
				self.show_info(self._("To display the content, you must enter a login name and password in the addon settings"), noexit=True)
			return False

		self.voyo = Voyo(self)
		if self.voyo.check_access_token() == False:
			self.voyo.login()

		return True

	# ##################################################################################################################

	def load_favorites(self):
		self.favorites = {}
		for cat in self.voyo.get_favorites():
			for item in cat['items']:
				self.favorites[item['id']] = True

	# ##################################################################################################################

	def root(self):
		PlayerFeatures.request_ffmpeg_mpd_support(self)
		self.load_favorites()

		self.add_search_dir()
		for cat in self.voyo.get_home():
			title = cat['title']
			if cat['type'] == 'live':
				self.add_dir(title, cmd=self.list_live_channels)
			elif cat['type'].endswith('content'):
				self.add_dir(title, cmd=self.add_items, items=cat['items'])
			elif cat['type'].startswith('page'):
				self.add_dir(title, cmd=self.list_category, id=cat['id'])

		self.add_dir(self._("Favorites"), cmd=self.list_favorites)
		self.add_dir(self._("Informations and settings"), cmd=self.list_info)

	# ##################################################################################################################

	def list_favorites(self):
		for cat in self.voyo.get_favorites():
			self.add_dir(cat['title'], cmd=self.add_items, items=cat['items'])

	# ##################################################################################################################

	def list_info(self):
		self.add_dir(self._("Profiles"), cmd=self.list_profiles)
		self.add_dir(self._("Devices"), cmd=self.list_devices)
		self.add_video(self._("Account informations"), cmd=self.account_info)

	# ##################################################################################################################

	def account_info(self):
		data = self.voyo.get_account_info()

		result = []
		result.append(self._("Name") + ': %s' % data['name'])
		result.append(self._("Customer ID") + ": %s" % data["id"])
		result.append(self._("Login from partner") + ": %s" % (self._("Yes") if data["from_partner"] else self._("No")))
		result.append("")
		result.append(self._("Active subscription") + ": %s (%s)" % (data["subscription_name"], data['subscription_type']))
		result.append("")
		result.append(self._("Number of registered devices") + ": %d" % data["devices_count"])

		self.show_info('\n'.join(result), noexit=True)

	# ##################################################################################################################

	def list_devices(self):
		for item in self.voyo.get_devices():
			plot = self._("Last used profile") + ':\n%s' % item['last_profile']
			title = item['name']
			if item['this']:
				title = _I(title)
			self.add_video(title, info_labels={'plot': plot}, cmd=self.delete_device, device_id=item['id'] if item['this'] == False else None )

	# ##################################################################################################################

	def delete_device(self, device_id):
		if device_id == None:
			return

		if self.get_yes_no_input(self._("Do you realy want to delete this device?")) == True:
			self.voyo.delete_device(device_id)
			self.refresh_screen()

	# ##################################################################################################################

	def list_profiles(self):
		for p in self.voyo.get_profiles():
			plot = []
			if p['is_main']:
				plot.append(self._("Main profile"))
			if p['is_child']:
				plot.append(self._("Kids profile"))

			if p['this']:
				title = _I(p['name'])
			else:
				title = p['name']

			self.add_video(title, img=p['img'], info_labels={'plot':'\n'.join(plot)}, cmd=self.switch_profile, profile_id=p['id'] if p['this'] == False else None)

	# ##################################################################################################################

	def switch_profile(self, profile_id):
		if profile_id == None:
			return

		if self.get_yes_no_input(self._("Do you realy want to switch profile?")) == True:
			self.voyo.switch_profile(profile_id)
			self.refresh_screen()

	# ##################################################################################################################

	def search(self, keyword, search_id=''):
		self.add_items(self.voyo.get_search_result(keyword))

	# ##################################################################################################################

	def load_info_labels(self, item_type, id):
		return self.voyo.get_item_info(item_type, id)

	# ##################################################################################################################

	def add_items(self, items):
		for item in items:
			title = item['title']
			typ = item['type']
			img = item['image']
			info_labels = partial(self.load_info_labels, item['type'], item['id'])

			menu = self.create_ctx_menu()
			if item['id'] in self.favorites:
				menu.add_menu_item(self._("Remove from favorites"), self.remove_fav, item_id=item['id'])
			else:
				menu.add_menu_item(self._("Add to favorites"), self.add_fav, item_id=item['id'])

			if typ == 'movie':
				self.add_video(title, img, info_labels=info_labels, menu=menu, cmd=self.play_item, item_id=item['id'], play_title=item['title'])
			elif typ == 'tvshow':
				self.add_dir(title, img, info_labels=info_labels, menu=menu, cmd=self.list_tvshow, item_id=item['id'])
			elif typ == 'episode':
				self.add_video(title, img, cmd=self.play_item, item_id=item['id'], play_title=item['title'])

	# ##################################################################################################################

	def add_fav(self, item_id):
		self.voyo.add_to_favorites(item_id)
		self.load_favorites()
		self.refresh_screen()

	# ##################################################################################################################

	def remove_fav(self, item_id):
		self.voyo.remove_from_favorites(item_id)
		self.load_favorites()
		self.refresh_screen()

	# ##################################################################################################################

	def list_live_channels(self):
		for item in self.voyo.list_live_channels():
			info_labels = item['epg']
			title = item['title'] + ' ' + _I(item['epg']['title'])
			self.add_video(title, item['image'], info_labels=info_labels, cmd=self.play_item, item_id=item['id'], play_title=item['title'])

	# ##################################################################################################################

	def list_category(self, id, page=1):
		self.add_items(self.voyo.list_category(id, page))
		self.add_next(cmd=self.list_category, id=id, page=page+1)

	# ##################################################################################################################

	def list_tvshow(self, item_id):
		for item in self.voyo.list_tvshow(item_id):
			if item['type'] == 'alike':
				self.add_dir(item['title'], cmd=self.add_items, items=item['items'])
			elif item['type'] == 'season':
				self.add_dir(item['title'], cmd=self.list_season, item_id=item_id, season_id=item['id'])
			elif item['type'] == 'episode':
				info_labels = {
					'duration': item['length']
				}
				self.add_video(item['title'], item['image'], info_labels=info_labels, cmd=self.play_item, item_id=item['id'], play_title=item['title'])

	# ##################################################################################################################

	def list_season(self, item_id, season_id):
		for item in self.voyo.list_season_episodes(item_id, season_id):
			info_labels = {
				'duration': item['length']
			}
			self.add_video(item['title'], item['image'], info_labels=info_labels, cmd=self.play_item, item_id=item['id'], play_title=item['title'])

	# ##################################################################################################################

	def get_dash_info(self, stream_key):
		data = self.scache.get(stream_key['key'])
		drm_info = data['drm_info']

		ret_data = {
			'url': data['url'],
			'bandwidth': stream_key['bandwidth'],
		}

		if drm_info['license_url'] and drm_info['license_key']:
			ret_data.update({
				'drm' : {
					'wv': {
						'license_url': drm_info['license_url'],
						'headers': {
							'X-AxDRM-Message': drm_info['license_key']
						}
					}
				}
			})

		return ret_data

	# ##################################################################################################################

	def get_hls_info(self, stream_key):
		return self.get_dash_info(stream_key)

	# ##################################################################################################################

	def resolve_dash_streams(self, url, video_title, drm_info):
		streams = self.get_dash_streams(url, self.voyo.req_session, max_bitrate=self.get_setting('max_bitrate'))
		if not streams:
			return

		data = {
			'url': streams[0]['playlist_url'],
			'drm_info': drm_info
		}

		cache_key = self.scache.put(data)
		for one in streams:
			key = {
				'key': cache_key,
				'bandwidth': one['bandwidth']
			}

			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('height', '720') + 'p'
			}
			self.add_play(video_title, stream_key_to_dash_url(self.http_endpoint, key), info_labels=info_labels)

	# ##################################################################################################################

	def resolve_hls_streams(self, url, video_title, drm_info):
		streams = self.get_hls_streams(url, self.voyo.req_session, max_bitrate=self.get_setting('max_bitrate'))
		if not streams:
			return

		data = {
			'url': streams[0]['playlist_url'],
			'drm_info': drm_info
		}

		cache_key = self.scache.put(data)
		for one in streams:
			key = {
				'key': cache_key,
				'bandwidth': one['bandwidth']
			}

			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('resolution', 'x720').split('x')[1] + 'p'
			}
			self.add_play(video_title, stream_key_to_hls_url(self.http_endpoint, key), info_labels=info_labels)

	# ##################################################################################################################

	def play_item(self, item_id, play_title):
		content = self.voyo.get_content_info(item_id)

		drm_info = {
			'license_url': content.get('licenseUrl'),
			'license_key': content.get('licenseKey')
		}

		if content['videoType'] == 'hls':
			self.resolve_hls_streams(content['videoUrl'], play_title, drm_info)
		else:
			self.resolve_dash_streams(content['videoUrl'], play_title, drm_info)

	# ##################################################################################################################
