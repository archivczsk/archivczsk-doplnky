# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate, CPModuleSearch
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.string_utils import _I, _C, _B, clean_html
from tools_archivczsk.date_utils import iso8601_to_datetime
from functools import partial
import sys, os

from datetime import datetime, timedelta
import time

from .ivysilani import iVysilani

ARCHIVE_MIN_YEAR = 2015

# ##################################################################################################################

# used for delayed translations
def _(s):
	return s

# ##################################################################################################################

class iVysilaniModuleLiveTV(CPModuleLiveTV):

	def get_live_tv_channels(self, cat_id=None):
		channels = self.cp.ivysilani.get_live_channels()
		data = self.cp.ivysilani.get_current_broadcast(channels)

		for item in data:
			cur_broadcast = (item.get('currentBroadcast') or {}).get('item')

			if not cur_broadcast:
				continue

			start_time = iso8601_to_datetime(cur_broadcast['start'])
			end_time = iso8601_to_datetime(cur_broadcast['end'])
			title_time = start_time.strftime('%H:%M') + ' - ' + end_time.strftime('%H:%M')

			menu = self.cp.create_ctx_menu()
			sidp = cur_broadcast.get('sidp')
			if sidp and len(sidp) > 1:
				self.cp.add_fav_ctx_menu(menu, cur_broadcast)
				channel_id = channels[item['channel']]['id']
			else:
				try:
					channel_data = self.cp.ivysilani.get_stream_data(cur_broadcast['idec'])
					channel_id = channel_data['platformChannel']
				except:
					channel_id = None

			info_labels = {
				'plot': '[{}]\n{}'.format(title_time, cur_broadcast.get('description') or '')
			}

			if channel_id:
				title = channels[item['channel']]['name']
			else:
				title = _C('gray', channels[item['channel']]['name'])

			title += _I( '  (' + cur_broadcast['title'] + ')' )
			self.cp.add_video(title, cur_broadcast['imageUrl'], info_labels, menu, cmd=self.play_channel, channel_id=channel_id)


	# ##################################################################################################################

	def play_channel(self, channel_id):
		try_nr = 0
		while try_nr < 3:
			data = self.cp.ivysilani.get_live_stream_data(channel_id)
			url = (data.get('streamUrls') or {}).get('main')
			if url:
				if self.cp.resolve_streams(url, title=data.get('title') or ''):
					break

			try_nr += 1


	# ##################################################################################################################

class iVysilaniModuleArchive(CPModuleArchive):
	def get_archive_channels(self):
		channels = self.cp.ivysilani.get_live_channels()
		archive_hours = int((datetime.now() - datetime(ARCHIVE_MIN_YEAR, 1, 1)).total_seconds() // 3600)

		for ch_str, channel in sorted(channels.items(), key=lambda x: x[1]['order']):
			if ch_str not in ('ctSportExtra', 'iVysilani'):
				if channel['img'] and (not channel['img'].endswith('.svg')):
					img = channel['img']
				else:
					img = os.path.join(self.cp.resources_dir, 'picture', 'logo_%s.png' % ch_str)
				self.add_archive_channel(channel['name'], ch_str, archive_hours, img, show_archive_len=False)

	# ##################################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		date_from, date_to = self.archive_day_to_datetime_range(archive_day)

		epg_list = self.cp.ivysilani.get_channel_epg(channel_id, date_from)

		for epg in epg_list:
			epg_start = iso8601_to_datetime(epg['start'])
			epg_stop = iso8601_to_datetime(epg['end'])
			title = "{:02}:{:02} - {:02d}:{:02d}".format(epg_start.hour, epg_start.minute, epg_stop.hour, epg_stop.minute)

			menu = self.cp.create_ctx_menu()

			if epg.get('idec') is not None and epg.get('isPlayableNow') == True and epg.get('liveOnly', False) == False:
				title = title + " - " + _I(epg["title"])
				self.cp.add_fav_ctx_menu(menu, epg)
			else:
				title = title + " - " + _C('grey', epg["title"])

			info_labels = {
				'plot': epg.get('description'),
				'duration': int(epg.get('length') or 0) * 60
			}

			self.cp.add_video(title, epg.get('imageUrl'), info_labels, menu, cmd=self.cp.play_idec, idec=epg.get('idec') if epg.get('isPlayableNow') == True else None)


# ##################################################################################################################

class iVysilaniModuleCategories(CPModuleTemplate):
	def __init__(self, content_provider, plot=None, img=None):
		CPModuleTemplate.__init__(self, content_provider, _("Categories"), plot, img)

	# ##################################################################################################################

	def root(self):
		data = self.cp.ivysilani.get_categories()

		for item in data:
			if item['categoryId'] is not None:
				self.cp.add_dir(item['title'], cmd=self.list_category, cat_id=item['categoryId'][0])

	# ##################################################################################################################

	def list_category(self, cat_id, subcategory=False, page=0):
		if subcategory == False:
			self.cp.add_dir(self._("Subcategories"), cmd=self.list_subcategories, cat_id = cat_id)

		data = self.cp.ivysilani.get_category_by_id(cat_id, page)

		for item in data['programmeFind']['items']:
			self.cp.add_media_item(item)


		if int(data['programmeFind']['totalCount']) > ((page+1) * self.cp.ivysilani.PAGE_SIZE):
			self.cp.add_next(cmd=self.list_category, cat_id=cat_id, subcategory=subcategory, page=page+1)

	# ##################################################################################################################

	def list_subcategories(self, cat_id):
		data = self.cp.ivysilani.get_categories()

		for item in data:
			if item['categoryId'] is not None and item['categoryId'][0] == str(cat_id):
				for child in item['children']:
					if child['categoryId'] is not None:
						if str(cat_id) in child['categoryId']:
							child['categoryId'].remove(str(cat_id))

						if len(child['categoryId']) > 0:
							self.cp.add_dir(child['title'], cmd=self.list_category, cat_id=child['categoryId'][0], subcategory=True)
				break


# ##################################################################################################################

class iVysilaniModuleRecommended(CPModuleTemplate):
	def __init__(self, content_provider, plot=None, img=None):
		CPModuleTemplate.__init__(self, content_provider, _("Recommended"), plot, img)

	# ##################################################################################################################

	def root(self, page=0):
		data = self.cp.ivysilani.get_homepage_rows(page)
		rows = (data['rows'] or [])
		for item in rows:
			if item['assets']['totalCount'] > 0:
				self.cp.add_dir(item['title'], cmd=self.list_block, block_id=item['id'])

#		API returns PAGE_SIZE results and next page is always empty
#		if len(rows) >= self.cp.ivysilani.PAGE_SIZE:
#			self.cp.add_next(cmd=self.root, page=page+1)

	# ##################################################################################################################

	def list_block(self, block_id, page=0):
		data = self.cp.ivysilani.get_homepage_block(block_id, page)

		assets = data.get('assets') or {}

		for item in (assets.get('items') or []):
			item['showType'] = 'movie' if (item.get('genres') or [{}])[0].get('title') == 'Film' else 'series'
			self.cp.add_media_item(item, add_show_title=True)

		if int(assets['totalCount']) > ((page+1) * self.cp.ivysilani.PAGE_SIZE):
			self.cp.add_next(cmd=self.list_block, block_id=block_id, page=page+1)

# ##################################################################################################################

class iVysilaniModuleFavourites(CPModuleTemplate):
	def __init__(self, content_provider, plot=None, img=None):
		CPModuleTemplate.__init__(self, content_provider, _("Favourites"), plot, img)

	# ##################################################################################################################

	def root(self):
		self.cp.ensure_supporter()
		for k, v in sorted(self.cp.favourites.items(), key=lambda x: x[1]['time'], reverse=True):
			info_labels = partial(self.load_info_labels, show_id=k)
			menu = self.cp.create_ctx_menu()
			self.cp.add_fav_ctx_menu(menu, {'id': k})
			if v.get('video'):
				self.cp.add_video(v['title'], None, info_labels, menu, cmd=self.cp.play_show, show_id=k)
			else:
				self.cp.add_dir(v['title'], None, info_labels, menu, cmd=self.cp.list_seasons, show_id=k)


	# ##################################################################################################################

	def load_info_labels(self, show_id):
		data = self.cp.ivysilani.get_show_info(show_id)

		return {
			'plot': data.get('description') or data.get('shortDescription'),
			'year': data.get('year'),
			'duration': data.get('duration'),
			'img': ((data.get('images') or {}).get('hero') or {}).get('mobile') or (data.get('images') or {}).get('card')
		}

# ##################################################################################################################

class iVysilaniContentProvider(ModuleContentProvider):

	def __init__(self, settings=None, data_dir=None, resources_dir=None, http_endpoint=None):
		ModuleContentProvider.__init__(self, 'iVysilani', settings=settings, data_dir=data_dir)
		self.resources_dir = resources_dir
		self.http_endpoint = http_endpoint
		self.favourites = {}
		self.ivysilani = iVysilani(self)
		self.load_favourites()

		self.modules = [
			CPModuleSearch(self),
			iVysilaniModuleLiveTV(self),
			iVysilaniModuleArchive(self),
			iVysilaniModuleCategories(self),
			iVysilaniModuleRecommended(self),
			iVysilaniModuleFavourites(self),
		]


	# ##################################################################################################################

	def load_favourites(self):
		self.favourites = self.load_cached_data('favourites')

	# #################################################################################################

	def save_favourites(self):
		self.save_cached_data('favourites', self.favourites)

	# ##################################################################################################################

	def add_fav(self, item):
		self.ensure_supporter()
		title = item.get('showTitle') or item['title']

		fav_item = {
			'time': int(time.time()),
			'title': title,
			'video': item.get('showType') not in ('series', 'magazine')  or 'idec' in item
		}

		show_id = item.get('showId') or item.get('id')
		self.favourites[show_id] = fav_item
		self.save_favourites()
		self.refresh_screen()

	# ##################################################################################################################

	def del_fav(self, item_id):
		if item_id in self.favourites:
			del self.favourites[item_id]
			self.save_favourites()
		self.refresh_screen()

	# ##################################################################################################################

	def add_fav_ctx_menu(self, menu, item):
		show_id = item.get('showId') or item.get('id')
		if show_id:
			menu.add_menu_item(self._("Show related"), cmd=self.list_related, show_id=show_id)

		item_id = item.get('id')
		if item_id:
			if item_id in self.favourites:
				menu.add_menu_item(self._("Remove from favourites"), cmd=self.del_fav, item_id=item_id)
			else:
				menu.add_menu_item(self._("Add to favourites"), cmd=self.add_fav, item=item)

	# ##################################################################################################################

	def list_series(self, idec, season_id=None, page=0):
		data = self.ivysilani.get_episodes(idec, page, season_id)

		for item in (data.get('items') or []):
			item['idec'] = item['id']
			self.add_media_item(item, add_season=(season_id == None))

		if int(data['totalCount']) > ((page+1) * self.ivysilani.PAGE_SIZE):
			self.add_next(cmd=self.list_series, idec=idec, season_id=season_id, page=page+1)

	# ##################################################################################################################

	def list_seasons(self, show_id):
		data = self.ivysilani.get_show_info(show_id)
		if data['seasons'] is None or len(data['seasons']) == 0:
			return self.list_series(data['idec'])

		self.add_dir(self._("All"), cmd=self.list_series, idec=data['idec'])
		for s in data['seasons']:
			self.add_dir(s['title'], cmd=self.list_series, idec=data['idec'], season_id=s['id'])

	# ##################################################################################################################

	def list_related(self, show_id, page=0):
		self.ensure_supporter()
		data = self.ivysilani.get_related_shows(show_id, page)

		for item in (data['items'] or []):
			self.add_media_item(item)

		if int(data['totalCount']) > ((page+1) * self.ivysilani.PAGE_SIZE):
			self.add_next(cmd=self.list_related, show_id=show_id, page=page+1)

	# ##################################################################################################################

	def add_media_item(self, item, add_season=False, add_show_title=False):
		menu = self.create_ctx_menu()
		self.add_fav_ctx_menu(menu, item)

		plot = item.get('description') or item.get('shortDescription')

		if item.get('lastBroadcast',{}).get('datetime'):
			bd = iso8601_to_datetime(item['lastBroadcast']['datetime'])
			plot = "[{}: {:02}.{:02}.{:04} {:02}:{:02}]\n{}".format(item['lastBroadcast']['channel'], bd.day, bd.month, bd.year, bd.hour, bd.minute, plot)

		genres = item.get('flatGenres') or item.get('genres') or []

		if 'children' in genres:
			genres = genres['children']

		info_labels = {
			'plot': plot,
			'year': item.get('year'),
			'genre': [x['title'] for x in genres],
			'duration': item.get('duration'),
			'title': item['title']
		}

		img = ((item.get('images') or {}).get('hero') or {}).get('mobile') or (item.get('images') or {}).get('card') or item.get('imageUrl') or item.get('previewImage')
		season  = (item.get('season') or {}).get('title')

		if add_show_title and item.get('showTitle'):
			title = '{}: {}'.format(item['showTitle'], item['title'])
		else:
			title = item['title']

		is_playable = item.get('playable', item.get('isPlayable', True))

		if is_playable:
			if season and add_season:
				title += ' [%s]' % _I(season)
		else:
			if season and add_season:
				title += ' [%s]' % season

			title = _C('grey', title)

		if item.get('showType') in ('series', 'magazine'):
			self.add_dir(title, img, info_labels, menu, cmd=self.list_seasons, show_id=item['id'])
		elif 'idec' in item:
			self.add_video(title, img, info_labels, menu, cmd=self.play_idec, idec=item.get('idec') if is_playable else None)
		else:
			self.add_video(title, img, info_labels, menu, cmd=self.play_show, show_id=item.get('id') if is_playable else None)

	# ##################################################################################################################

	def play_show(self, show_id):
		if not show_id:
			return

		data = self.ivysilani.get_show_info(show_id)
		return self.play_idec(data['idec'])

	# ##################################################################################################################

	def play_idec(self, idec):
		if not idec:
			return

		data = self.ivysilani.get_stream_data(idec)
		streams = data.get('streams',[{}])[0]

		subs = None
		for s in (streams.get('subtitles') or []):
			if s.get('language') == 'ces':
				for f in s.get('files', []):
					if f.get('format') == 'vtt':
						subs = f.get('url')
						break

		title = data.get('episodeTitle') or data.get('showTitle') or data.get('title')
		self.resolve_streams(streams.get('url'), subs=subs, title=title)

	# ##################################################################################################################

	def search(self, keyword, search_id='', page=0):
		self.ensure_supporter()
		data = self.ivysilani.search_shows(keyword, page)

		for item in (data['items'] or []):
			item['showType'] = 'movie' if (item.get('genres') or [{}])[0].get('title') == 'Film' else 'series'
			self.add_media_item(item)

		if int(data['totalCount']) > ((page+1) * self.ivysilani.PAGE_SIZE):
			self.add_next(cmd=self.search, keyword=keyword, page=page+1)

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
			'subs': stream_key['subs'],
			'drm' : {
				'licence_url': 'https://ivys-wvproxy.o2tv.cz/license?access_token=c3RlcGFuLWEtb25kcmEtanNvdS1wcm9zdGUtbmVqbGVwc2k='
			}
		}

	# ##################################################################################################################

	def resolve_streams(self, manifest_url, subs=None, title=''):
		if not manifest_url:
			return False

		if 'streamType=hls' in manifest_url:
			subs_enabled = self.get_setting('subtitles') != 'disabled'

			streams = self.get_hls_streams(manifest_url, max_bitrate=self.get_setting('max_bitrate'))
			if not streams:
				return False

			for s in streams:
				url = stream_key_to_hls_url(self.http_endpoint, {'url': s['playlist_url'], 'bandwidth': s['bandwidth']} )

				bandwidth = int(s['bandwidth'])

				if bandwidth >= 6272000:
					quality = "1080p"
				elif bandwidth >= 3712000:
					quality = "720p"
				elif bandwidth >= 2176000:
					quality = "576p"
				elif bandwidth >= 1160000:
					quality = "404p"
				elif bandwidth >= 628000:
					quality = "288p"
				else:
					quality = "144p"

				info_labels = {
					'bandwidth': int(s['bandwidth']),
					'quality': quality
				}

				self.add_play(title, url, info_labels=info_labels, subs=subs if subs_enabled else None)
		else:
			subs_subsupport = self.get_setting('subtitles') == 'subssupport'

			streams = self.get_dash_streams(manifest_url, max_bitrate=self.get_setting('max_bitrate'))
			if not streams:
				return False

			for s in streams:
				url = stream_key_to_dash_url(self.http_endpoint, {'url': s['playlist_url'], 'bandwidth': s['bandwidth'], 'subs': subs})

				info_labels = {
					'bandwidth': int(s['bandwidth']),
					'quality': s['height'] + 'p' if s.get('height') else "720p"
				}

				self.add_play(title, url, info_labels=info_labels, subs=subs if subs_subsupport else None)

		return True

	# ##################################################################################################################
