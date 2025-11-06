# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.string_utils import _I, _C, _B, int_to_roman
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from functools import partial

from Plugins.Extensions.archivCZSK.colors import DeleteColors

from time import time
from .jojplay import JojPlay
from .videoportal import JojVideoportal

class JojPlayContentProvider(CommonContentProvider):
	def __init__(self, settings=None, data_dir=None, http_endpoint=None):
		CommonContentProvider.__init__(self, 'JojPlay', settings=settings, data_dir=data_dir)
		self.http_endpoint = http_endpoint
		self.login_settings_names = ('username', 'password')
		self.jojplay = JojPlay(self)
		self.videoportal = JojVideoportal(self)
		self.tmp_dir = '/tmp/'
		self.epg = {}

	# ##################################################################################################################

	def login(self, silent):
		self.jojplay.login()
		return True

	# ##################################################################################################################

	def root(self):
		self.select_profile_on_startup()

		self.add_dir(self._("Search"), cmd=self.list_search)
		self.add_dir(self._("Live TV"), cmd=self.list_row, row_id='livetv')

		for s in self.jojplay.get_root_screens():
			self.add_dir(s['title'], cmd=self.list_screen, screen_id=s['id'], ref=True)

		# Listing genres is possible, but I have not found a way to list items by genre ... :-(
#		self.add_dir(self._("By genres"), cmd=self.list_genres)

		self.add_dir(self._("List of shows"), img='http://videoportal.joj.sk/html/assets/logo.png', cmd=self.videoportal.root)

		self.add_dir(self._("Favourites"), cmd=self.list_favourites)

		if self.get_setting("sync_playback"):
			self.add_dir(self._("Continue watching"), cmd=self.list_watchlist)

	# ##################################################################################################################

	def select_profile_on_startup(self):
		if self.get_setting('select_profile') == False:
			return

		profiles = self.jojplay.get_profiles()

		if len(profiles) < 2:
			return

		choices = []
		for i, p in enumerate(profiles):
			if p['active']:
				title = _I(p['name'])
			else:
				title = p['name']

			choices.append(title)

		answer = self.get_list_input(choices, self._("Select profile"))
		if answer == -1:
			return

		profile = profiles[answer]
		if profile['active']:
			return

		self.jojplay.set_current_profile(profile['id'])

	# ##################################################################################################################

	def list_search(self):
		self.ensure_supporter()
		self.add_search_dir(self._("Search movies"), 'videos')
		self.add_search_dir(self._("Search series"), 'series')

	# ##################################################################################################################

	def search(self, keyword, search_id):
		for item in self.jojplay.search(keyword, search_id == 'videos'):
			self.add_item_uni(item, search_id == 'videos')

	# ##################################################################################################################

	def reset_watch_position(self, item):
		data_item = self.jojplay.get_item_details('video', item['id'])
		self.jojplay.add_watch_position(data_item.get('duration'), 0, item['id'], item.get('parent_tag_id'), data_item.get('episodeNumber'), data_item.get('seasonNumber'))
		self.refresh_screen()

	# ##################################################################################################################

	def add_favourite(self, item_type, item_id):
		self.jojplay.add_favourite(item_type, item_id)
		self.refresh_screen()

	# ##################################################################################################################

	def remove_favourite(self, item_type, item_id):
		self.jojplay.remove_favourite(item_type, item_id)
		self.refresh_screen()

	# ##################################################################################################################

	def list_favourites(self, item_type=None):
		if item_type == None:
			self.add_dir(self._("Movies"), cmd=self.list_favourites, item_type='video')
			self.add_dir(self._("Series"), cmd=self.list_favourites, item_type='tag')
			return

		for item in self.jojplay.get_favourites(item_type):
			self.add_item_uni(item)

	# ##################################################################################################################

	def list_watchlist(self):
		for item in self.jojplay.get_watchlist():
			self.add_item_uni(item, full_title=True)

	# ##################################################################################################################

	def list_related(self, item_id):
		for item in self.jojplay.get_related_videos(item_id):
			self.add_item_uni(item, True)

	# ##################################################################################################################

	def get_ctx_menu(self, item):
		menu = self.create_ctx_menu()

		item_id = item.get('id')
		item_type = item.get('type')

		if item_type in ('video', 'tag'):
			is_fav = self.jojplay.is_favourite(item_type, item_id)

			if is_fav == True:
				menu.add_menu_item(self._("Remove from favourites"), cmd=self.remove_favourite, item_type=item_type, item_id=item_id)
			elif is_fav == False:
				menu.add_menu_item(self._("Add to favourites"), cmd=self.add_favourite, item_type=item_type, item_id=item_id)

		if item['type'] == 'video':
			menu.add_media_menu_item(self._("Play trailer"), cmd=self.resolve_trailer, item_id=item_id)
			menu.add_menu_item(self._("Show related"), cmd=self.list_related, item_id=item.get('id'))
			menu.add_menu_item(self._("Reset watch position"), cmd=self.reset_watch_position, item=item)

		return menu

	# ##################################################################################################################

	def load_info_labels(self, item):
		if item['type'] not in ('video', 'tag'):
			return {}

		data = self.jojplay.get_item_details(item['type'], item['id'])

		if item.get('playable') == 0:
			plot_prefix = '[{}]\n'.format(self._("Subscription needed"))
		elif item.get('playable') == 2 and not self.is_supporter():
			plot_prefix = '[{}]\n'.format(self._("Only for ArchivCZSK supporters"))
		else:
			plot_prefix = None

		plot = self.jojplay.get_lang_label(data.get('description'))

		title = None
		ext = data.get('externals', {})
		if ext.get('tvProfiType') in ('show',):
			title = ext.get('tvProfiSeriesName')

			if title and data.get('episodeNumber'):
				title += ' {} ({})'.format(int_to_roman(data.get('seasonNumber', 0)), data['episodeNumber'])

		return {
			'plot': plot_prefix + plot if plot_prefix else plot,
			'duration': int(data.get('duration', 0) // 1000) or None,
			'img': self.jojplay.get_img(data),
			'title': title
		}

	# ##################################################################################################################

	def get_current_epg(self, channel_id, virtual):
		if virtual:
			epg = self.jojplay.get_virtual_channel_current_epg(channel_id)
		else:
			epg = self.jojplay.get_channel_current_epg(channel_id)

		return epg

	# ##################################################################################################################

	def _mark_playability(self, title, playable):
		if playable == 0:
			title = DeleteColors(title)
			title = _C('gray', title) + _I(' *')
		elif playable == 2 and not self.is_supporter():
			title += _I(' *')

		return title

	# ##################################################################################################################

	def _fill_epg(self, item):
		title = item['title']
		info_labels = {'plot': ''}

		epg = self.get_current_epg(item.get('id'), virtual=item.get('virtual'))
		if epg:
			info_labels['plot'] = '[{} - {}]\n{}'.format(self.timestamp_to_str(epg['from']), self.timestamp_to_str(epg['to']), epg['plot'])
			title += _I(' ({})'.format(epg['title']))

		if item.get('playable') == 0:
			info_labels['plot'] = '[{}]\n{}'.format(self._("Subscription needed"), info_labels['plot'])
		elif item.get('playable') == 2 and not self.is_supporter():
			info_labels['plot'] = '[{}]\n{}'.format(self._("Only for ArchivCZSK supporters"), info_labels['plot'])

		return title, info_labels, epg.get('video_id'), epg.get('from',0)

	# ##################################################################################################################

	def _make_full_title(self, item):
		if item.get('parent_tag_id'):
			data = self.jojplay.get_item_details('tag', item['parent_tag_id'])
			title = '{}: {}'.format(self.jojplay.get_lang_label(data.get('name','')), _I(item['title']))
		else:
			title = item['title']

		return title

	# ##################################################################################################################

	def add_item_uni(self, item, full_title=False):
		info_labels = partial(self.load_info_labels, item=item)

		title = item['title']
		playable = item.get('playable')
		menu = self.get_ctx_menu(item)

		if item['type'] == 'fav':
			self.add_dir(title, item.get('img'), info_labels, menu, cmd=self.list_favourites)
		elif item['type'] == 'watchlist':
			self.add_dir(title, item.get('img'), info_labels, menu, cmd=self.list_watchlist)
		elif item['type'] == 'row':
			self.add_dir(title, item.get('img'), info_labels, menu, cmd=self.list_row, row_id=item['id'])
		elif item['type'] == 'tag':
			self.add_dir(title, item.get('img'), info_labels, menu, cmd=self.list_tag, tag_id=item['id'])
		elif item['type'] == 'video':
			if full_title:
				title = self._make_full_title(item)
			self.add_video(self._mark_playability(title, playable), item.get('img'), info_labels, menu, cmd=self.resolve_video, item=item)
		elif item['type'] == 'tvChannel':
			title, info_labels, virtual_id, virtual_from = self._fill_epg(item)
			if virtual_id:
				item['virtual_id'] = virtual_id
				item['virtual_from'] = virtual_from
			self.add_video(self._mark_playability(title, playable), item.get('img'), info_labels, menu, cmd=self.resolve_video, item=item)
		else:
			self.log_error("Unsupported item type: '%s'" % item['type'])

	# ##################################################################################################################

	def list_screen(self, screen_id, page=0, ref=False):
		for item in self.jojplay.get_screen_items(screen_id, page, ref):
			if item['type'] == 'next':
				self.add_next(self.list_screen, screen_id=screen_id, page=page+1, ref=ref)
			else:
				self.add_item_uni(item)

	# ##################################################################################################################

	def list_row(self, row_id, page=0):
		for item in self.jojplay.get_row_items(row_id, page):
			if item['type'] == 'next':
				self.add_next(self.list_row, row_id=row_id, page=page+1)
			else:
				self.add_item_uni(item)

	# ##################################################################################################################

	def list_tag(self, tag_id):
		data = self.jojplay.get_tag_data(tag_id)
		item = self.jojplay._add_tag_item(data[0])
		return self.list_series(item['id'], item.get('seasons'))

	# ##################################################################################################################

	def list_series(self, tag_id, seasons=None):
		if seasons and len(seasons) > 1:
			for s in seasons:
				self.add_dir('{}: {:02}'.format(self._("Season"), s), cmd=self.list_season, tag_id=tag_id, season=s)
		else:
			return self.list_season(tag_id, seasons[0] if seasons else None)

	# ##################################################################################################################

	def list_season(self, tag_id, season=None):
		for item in self.jojplay.get_serie_videos(tag_id, season=season):
			self.add_item_uni(item)

	# ##################################################################################################################

	def list_genres(self):
		for item in self.jojplay.get_genres():
			self.add_dir(item['title'], cmd=self.list_genre, genre_id=item['id'])

	# ##################################################################################################################

	def list_genre(self, genre_id):
		# TODO: not working ... need to investigate how to list items by genre (probably not possible)
		x=self.jojplay.client.load_genre_items(genre_id)
		self.jojplay.client.dump_json('genre-%s' % genre_id, x, True)

	# ##################################################################################################################

	def get_hls_info(self, stream_key):
		return {
			'url': stream_key['url'],
			'bandwidth': stream_key['bandwidth'],
		}

	# ##################################################################################################################

	def get_dash_info(self, stream_key):
		return {
			'url': stream_key['url'],
			'bandwidth': stream_key['bandwidth'],
		}

	# ##################################################################################################################

	def resolve_streams(self, manifest_url, title='', data_item=None, play_pos=None, resume_popup=True):
		if not manifest_url:
			return False

		player_settings = {}
		if self.silent_mode == False and play_pos:
			player_settings.update({
				'resume_time_sec': play_pos,
				"resume_popup": resume_popup,
			})

		supporter = self.is_supporter()
		if manifest_url.endswith('.m3u8'):
			streams = self.get_hls_streams(manifest_url, self.jojplay.client.req_session, max_bitrate=self.get_setting('max_bitrate'))
			if not streams:
				return False

			for s in streams:
				url = stream_key_to_hls_url(self.http_endpoint, {'url': s['playlist_url'], 'bandwidth': s['bandwidth']} )

				bandwidth = int(s['bandwidth'])

				if bandwidth >= 5272000:
					quality = "1080p"
					if not supporter:
						continue
				elif bandwidth >= 3212000:
					quality = "720p"
				elif bandwidth >= 1460000:
					quality = "404p"
				elif bandwidth >= 628000:
					quality = "288p"
				else:
					quality = "144p"

				info_labels = {
					'bandwidth': int(s['bandwidth']),
					'quality': quality
				}

				self.add_play(title, url, info_labels=info_labels, data_item=data_item, settings=player_settings)
		else:
			streams = self.get_dash_streams(manifest_url, self.jojplay.client.req_session, max_bitrate=self.get_setting('max_bitrate'))
			if not streams:
				return False

			for s in streams:
				url = stream_key_to_dash_url(self.http_endpoint, {'url': s['playlist_url'], 'bandwidth': s['bandwidth']})

				info_labels = {
					'bandwidth': int(s['bandwidth']),
					'quality': s['height'] + 'p' if s.get('height') else "720p"
				}

				if not supporter and int(info_labels['quality'][:-1]) > 720:
					continue

				self.add_play(title, url, info_labels=info_labels, data_item=data_item, settings=player_settings)

		return True

	# ##################################################################################################################

	def resolve_video(self, item):
		video_id=item.get('id')
		trailer_id = None
		play_pos = None

		if not video_id:
			return

		if item.get('playable') == 2:
			self.ensure_supporter()

		if item.get('playable') == 0:
			self.log_info("Video is marked as not playable - checking trailer")

			data_item = self.jojplay.get_item_details('video', video_id)
			trailer_id = data_item.get('linkedVideos',[{}])[0].get('videoRef','').split('/')[-1]
			if trailer_id:
				# we have trailer - ask user if we should play it
				if self.get_yes_no_input(self._("This video is not available for your subscription. Play trailer instead?")) == False:
					return

				self.ensure_supporter()
			else:
				return

		if item['type'] == 'tvChannel':
			data_item = None
			if item.get('virtual'):
				item_type = 'video'
				trailer_id = item.get('virtual_id')
				play_pos = int(time()) - item.get('virtual_from', int(time()))
			else:
				item_type = 'tvChannel'
		elif item['type'] == 'trailer':
			data_item = None
			item_type = 'video'
		else:
			item_type = 'video'
			data_item = self.jojplay.get_item_details('video', video_id)
			# convert data item do usable form
			data_item = {
				'episode': data_item.get('episodeNumber'),
				'season': data_item.get('seasonNumber'),
				'duration': data_item.get('duration'),
				'video_id': video_id,
				'tag_id': item.get('parent_tag_id'),
			}

		url = self.jojplay.get_video_source_url(trailer_id or video_id, item_type)
		self.log_debug("Resolved video URL: %s" % url )
		return self.resolve_streams(url, item['title'], data_item, play_pos or self.jojplay.get_play_pos(video_id), play_pos == None)

	# ##################################################################################################################

	def resolve_trailer(self, item_id):
		item = self.jojplay.get_item_details('video', item_id)
		trailer_id = item.get('linkedVideos',[{}])[0].get('videoRef','').split('/')[-1]

		if trailer_id:
			self.ensure_supporter()
			return self.resolve_video({'type': 'video', 'title': 'Trailer', 'id': trailer_id})

	# ##################################################################################################################

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		if position == None or data_item == None:
			return

		if action in ('watching', 'end'):
			if action == 'end' and duration and position >= (duration-10):
				# mark item as viewed
				position = data_item['duration']

			self.jojplay.add_watch_position(data_item['duration'], position * 1000, data_item['video_id'], data_item['tag_id'], data_item['episode'], data_item['season'])

	# ##################################################################################################################
