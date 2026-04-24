# -*- coding: utf-8 -*-
from datetime import datetime
from time import time
import json, base64, os
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.contentprovider.provider import CommonContentProvider, InfoLabels
from tools_archivczsk.contentprovider.exception import AddonInfoException
from tools_archivczsk.date_utils import iso8601_to_datetime
from tools_archivczsk.simple_config import SimpleConfigSelection, SimpleConfigInteger, SimpleConfigYesNo, SimpleConfigMultiSelection
from tools_archivczsk.compat import urlparse

from .stremio import StremioClient, StremioServiceClient, STREMIO_PAGE_SIZE, clean_str
from .watched import StremioWatched

import threading

try:
	unicode
except:
	unicode = str

# needed for translations
def _(s):
	return s

_tr_list = [
	_('Movie'),
	_('Series'),
	_('Channel'),
	_('Other'),
]

# #################################################################################################

class StremioContentProvider(CommonContentProvider):

	def __init__(self):
		CommonContentProvider.__init__(self)
		self.login_optional_settings_names = ('username', 'password')
		self.dubbed_lang_list = ['en']
		self.lang_list = ['en']
		self.stremio = StremioClient(self)
		self.service = StremioServiceClient(self)
		self.watched = StremioWatched(self)
		self.home_items = []
		self.adult_addons = {}
		self.adult_catalogs = {}
		self.play_time = 0

		# hack to handle compatibility with ArchivCZSK, because in stremio 'movie' can be anything and here we need to know if it is single video or collection
		self.collection_prefixes = ('tvdbc:',)
		self.load_adults_data()

	# ##################################################################################################################

	def login(self, silent):
		self.build_lang_lists()

		if self.stremio.logged_in():
			return True
		else:
			if silent:
				return False

		self.stremio.login()

		return True

	# ##################################################################################################################

	def get_dubbed_lang_list(self):
		dl = self.get_setting('dubbed-lang')

		if dl == 'auto':
			lang_code = self.get_lang_code()
			if lang_code == 'cs':
				return ['cs', 'sk']
			elif lang_code == 'sk':
				return ['sk', 'cs']
			else:
				return [lang_code]
		else:
			return dl.split('+')

	# ##################################################################################################################

	def build_lang_lists(self):
		self.dubbed_lang_list = self.get_dubbed_lang_list()
		self.lang_list = self.dubbed_lang_list[:]
		if 'en' not in self.lang_list:
			self.lang_list.append('en')

	# #################################################################################################

	def root(self):
		self.build_lang_lists()
		self.stremio.load_addons()
		self.service.reinit()
		self.home_items = self.load_cached_data('home').get('items',[])

		self.add_search_dir()
		self.add_dir(self._("Last viewed"), cmd=self.list_last_viewed)

		if self.home_items:
			self.add_dir(self._("Home"), cmd=self.list_home)
			self.add_dir(self._("Discover"), cmd=self.list_discover)
		else:
			# if we don't have anything on home screen, then directly list discover page here
			self.list_discover()

	# #################################################################################################

	def list_home(self):
		for i, item in enumerate(self.home_items):
			menu = self.create_ctx_menu()
			menu.add_menu_item(self._("Remove from home screen"), cmd=self.remove_from_home, item=item)

			if i > 0:
				menu.add_menu_item(self._("Move up"), cmd=self.home_item_move, item=item, direction='up')

			if i < len(self.home_items) - 1:
				menu.add_menu_item(self._("Move down"), cmd=self.home_item_move, item=item, direction='down')

			data = item.get('data', {})
			if data.get('addon_id'):
				addon = self.stremio.get_addon(data['addon_id'])

				if not addon:
					self.log_error("Addon %s not found - ignoring home item %s" % (data['addon_id'], item['title']))
					continue

			il = InfoLabels(item.get('title'))

			if item['type'] == 'addon':
				il.short_desc = [
					'[{}]'.format(addon.version),
					addon.description or ''
				]
				il.adult = self.is_adult(addon.addon_id)
				self.add_adult_management(menu, addon.addon_id)
				self.add_dir(il, data.get('img'), menu, cmd=self.list_addon_root, addon_id=data['addon_id'])
			elif item['type'] == 'catalog_type':
				il.short_desc = addon.name
				il.adult = self.is_adult(data['addon_id'])
				self.add_dir(il, menu=menu, cmd=self.list_catalog_root, addon_id=data['addon_id'], cat_type=data['cat_type'])
			elif item['type'] == 'catalog':
				il.short_desc = [
					addon.name,
					self._(data['cat_type'].capitalize())
				]
				il.adult = self.is_adult(data['addon_id'], data['cat_type'], data['cat_id'])
				self.add_adult_management(menu, addon.addon_id, data['cat_type'], data['cat_id'])
				self.add_dir(il, menu=menu, cmd=self.list_catalog, addon_id=data['addon_id'], cat_type=data['cat_type'], cat_id=data['cat_id'], params=item.get('params'), extra=data['extra'])
			else:
				self.log_error("Unsupported home item: %s" % item['type'])


	# #################################################################################################

	def list_discover(self):
		for t in self.stremio.get_catalog_types():
			self.add_dir(self._(t.capitalize()), cmd=self.list_catalog_root, cat_type=t)

		self.add_dir(self._('Addons'), cmd=self.list_addons)

	# #################################################################################################

	def list_last_viewed(self, item_type=None):
		if item_type == None:
			for t in self.stremio.get_catalog_types():
				self.log_debug("Requesting last viewed items of type '%s'" % t)
				if self.watched.get(t):
					self.add_dir(self._(t.capitalize()), cmd=self.list_last_viewed, item_type=t)
				else:
					self.log_debug("No last viewed items of type '%s'" % item_type)
			return

		for item_id in self.watched.get(item_type):
			il = self.load_cached_item(item_type, item_id)
			if il.title:
				menu = self.create_ctx_menu()
				menu.add_menu_item(self._("Remove from seen"), cmd=self.remove_last_seen, item_type=item_type, item_id=item_id)

				search_query = il.search_query()

				if item_type in ('movie', 'tv') and not item_id.startswith(self.collection_prefixes):
					self.add_video(il, menu=menu, cmd=self.resolve_stream, video_title=il.format_title(False), item_type=item_type, item_id=item_id, streams=getattr(il, 'streams', None), search_query=search_query)
				else:
					self.add_dir(il, menu=menu, cmd=self.list_videos, addon_id=None, item_type=item_type, item_id=item_id, search_query=search_query)


	# #################################################################################################

	def remove_last_seen(self, item_type, item_id):
		self.watched.remove(item_type, item_id)
		self.watched.save()
		self.refresh_screen()

	# #################################################################################################

	def home_item_move(self, item, direction):
		try:
			idx = self.home_items.index(item)
		except:
			self.log_error("Item not found on home screen")
			self.refresh_screen()
			return

		if direction == 'up':
			if idx > 0:
				x = self.home_items.pop(idx)
				self.home_items.insert(idx-1, x)
		elif direction == 'down':
			if idx < len(self.home_items) - 1:
				x = self.home_items.pop(idx)
				self.home_items.insert(idx+1, x)

		self.save_cached_data('home', {'items': self.home_items})
		self.refresh_screen()

	# #################################################################################################

	def add_to_home(self, item_type, item_data, item_name=None):
		item_name = self.get_text_input(self._("Enter home screen item name"), text=item_name or '')

		if item_name:
			item = {
				'title': item_name,
				'type': item_type,
				'data': item_data
			}
			extra = item_data.get('extra')
			if extra:
				params = self.get_advanced_filter_params(extra)
				item['params'] = params

			self.home_items.append(item)
			self.save_cached_data('home', {'items': self.home_items})

		self.refresh_screen()

	# #################################################################################################

	def remove_from_home(self, item):
		self.home_items.remove(item)
		self.save_cached_data('home', {'items': self.home_items})
		self.refresh_screen()

	# #################################################################################################

	def load_adults_data(self):
		adult = self.load_cached_data('adult')
		self.adult_addons = { a: True for a in adult.get('addons',[])}
		self.adult_catalogs = { c: True for c in adult.get('catalogs',[])}

	# #################################################################################################

	def add_to_adult(self, addon_id, cat_type=None, cat_id=None):
		if cat_id:
			key = '{}:{}:{}'.format(addon_id, cat_type, cat_id)
			self.adult_catalogs[key] = True
			self.update_cached_data('adult', {'catalogs': list(self.adult_catalogs.keys())})
		else:
			self.adult_addons[addon_id] = True
			self.update_cached_data('adult', {'addons': list(self.adult_addons.keys())})

		self.refresh_screen()

	# #################################################################################################

	def remove_from_adult(self, addon_id, cat_type=None, cat_id=None):
		if cat_id:
			key = '{}:{}:{}'.format(addon_id, cat_type, cat_id)
			if key in self.adult_catalogs:
				del self.adult_catalogs[key]
				self.update_cached_data('adult', {'catalogs': list(self.adult_catalogs.keys())})
		else:
			if addon_id in self.adult_addons:
				del self.adult_addons[addon_id]
				self.update_cached_data('adult', {'addons': list(self.adult_addons.keys())})

		self.refresh_screen()

	# #################################################################################################

	def is_adult(self, addon_id, cat_type=None, cat_id=None, check_manifest=True):
		if check_manifest:
			addon = self.stremio.get_addon(addon_id)

			if (addon and addon.is_adult()) or self.adult_addons.get(addon_id):
				return True

		if cat_id:
			return self.adult_catalogs.get( '{}:{}:{}'.format(addon_id, cat_type, cat_id) )
		else:
			return self.adult_addons.get(addon_id)

	# #################################################################################################

	def add_adult_management(self, menu, addon_id, cat_type=None, cat_id=None):
		if self.get_parental_settings('unlocked'):
			if self.is_adult(addon_id, cat_type, cat_id, check_manifest=False):
				menu.add_menu_item(self._("Unmark as adult"), self.remove_from_adult, addon_id=addon_id, cat_type=cat_type, cat_id=cat_id)
			else:
				menu.add_menu_item(self._("Mark as adult"), self.add_to_adult, addon_id=addon_id, cat_type=cat_type, cat_id=cat_id)

	# #################################################################################################

	def search(self, keyword, search_id, page=0):
		self.log_debug("Search called with keyword: '%s' and search_id: %s" % (keyword, search_id))

		if not isinstance(search_id, dict):
			search_id = {}

		if not search_id.get('type'):
			# type is mandatory, so let user select the right one
			cat_types = list(self.stremio.get_catalog_types(search_id.get('id')))

			if not cat_types:
				return

			idx = self.get_list_input( [self._(t.capitalize()) for t in cat_types], self._("Select what to search"))
			if idx == -1:
				return

			search_id['type'] = cat_types[idx]

		if not search_id.get('id') or not search_id.get('cat_id'):
			# no addon ID provided - search using all
			for aid, cat_list in self.stremio.get_catalogs_list(addon_id=search_id.get('id'), cat_type=search_id['type']):
				for c in cat_list:
					if self.stremio.supports_search(c.get('extra')):
						self.search(keyword, self.create_search_id(aid, c['type'], c['id'], c.get('extra')), page=None)

			return


		addon = self.stremio.get_addon(search_id['id'])
		extra = search_id.get('extra')
		supports_filtering = self.stremio.supports_filtering(extra)
		is_adult = self.is_adult(addon.addon_id, search_id['type'], search_id['cat_id'])

		items = addon.search(search_id['type'], search_id['cat_id'], keyword, search_id.get('params') or self.stremio.build_default_params(extra), page=page)
		for item in items:
			if supports_filtering:
				menu = self.create_ctx_menu()
				menu.add_menu_item(self._("Advanced filtering"), cmd=self.advanced_search_filter, keyword=keyword, search_id=search_id, update_content=search_id.get('params'))
			else:
				menu = {}

			self.add_item_uni(search_id['id'], item, menu, is_adult)

		# page == None -> disable paging
		if page != None and len(items) >= STREMIO_PAGE_SIZE and self.stremio.supports_paging(extra):
			self.add_next(cmd=self.search, search_id=search_id, keyword=keyword, page=page+1)

	# #################################################################################################

	def list_addons(self):
		for a in self.stremio.get_catalog_addons():
			il = InfoLabels(a.name)
			il.short_desc = [
				'[{}]'.format(a.version),
				a.description or ''
			]
			il.adult = self.is_adult(a.addon_id)

			menu = self.create_ctx_menu()
			menu.add_menu_item(self._("Add to home screen"), cmd=self.add_to_home, item_type='addon', item_name=a.name, item_data={'addon_id': a.addon_id, 'img': a.logo})
			self.add_adult_management(menu, a.addon_id)
			self.add_dir(a.name, a.logo, il(), menu, cmd=self.list_addon_root, addon_id=a.addon_id)

	# #################################################################################################

	def list_addon_root(self, addon_id):
		addon = self.stremio.get_addon(addon_id)
		types = addon.get_catalog_types()

		if any(self.stremio.supports_search(c.get('extra')) for c in addon.get_catalogs_list()):
			self.add_search_dir(search_id=self.create_search_id(addon_id, None, None))

		if len(types) == 1:
			return self.list_catalog_root(addon_id, list(types)[0])

		for t in types:
			menu = self.create_ctx_menu()
			menu.add_menu_item(self._("Add to home screen"), cmd=self.add_to_home, item_type='catalog_type', item_name=self._(t.capitalize()), item_data={'addon_id': addon_id, 'cat_type': t})
			il = InfoLabels(self._(t.capitalize()))
			il.short_desc = addon.name
			self.add_dir(il, menu=menu, cmd=self.list_catalog_root, addon_id=addon_id, cat_type=t)

	# #################################################################################################

	def create_search_id(self, addon_id, cat_type, cat_id, extra=None):
		return {'id': addon_id, 'type': cat_type, 'cat_id':cat_id, 'extra': extra}

	# #################################################################################################

	def parse_search_id(self, search_id):
		return json.loads(base64.b64decode(search_id.encode('ascii')).decode('utf-8'))

	# #################################################################################################

	def list_catalog_root(self, addon_id=None, cat_type=None):
		for aid, cat_list in self.stremio.get_catalogs_list(addon_id, cat_type):
			for c in cat_list:
#				self.log_debug("Processing %s catalog: %s" % (aid, c))
				extra = c.get('extra')
				title = c.get('name') or c.get('id')
				title = clean_str(title)

				il = InfoLabels(title)
				il.short_desc = [
					self.stremio.get_addon(aid).name,
					self._(c['type'].capitalize())
				]
				il.adult = self.is_adult(aid, c['type'], c['id'])

				if self.stremio.supports_search(extra, True):
					self.add_search_dir(il, self.create_search_id(aid, c['type'], c['id']))
				else:
					menu = self.create_ctx_menu()
					menu.add_menu_item(self._("Add to home screen"), cmd=self.add_to_home, item_type='catalog', item_name=title, item_data={'addon_id': aid, 'cat_type': c['type'], 'cat_id': c['id'], 'extra': extra})
					self.add_adult_management(menu, aid, c['type'], c['id'])
					self.add_dir(il, menu=menu, cmd=self.list_catalog, addon_id=aid, cat_type=c['type'], cat_id=c['id'], extra=extra)

	# #################################################################################################

	def list_catalog(self, addon_id, cat_type, cat_id, extra=None, params=None, page=0):
		if self.stremio.supports_search(extra):
			self.add_search_dir(search_id=self.create_search_id(addon_id, cat_type, cat_id, extra))

		addon = self.stremio.get_addon(addon_id)
		items = addon.get_catalog(cat_type, cat_id, params=params or self.stremio.build_default_params(extra), page=page)

		supports_filtering = self.stremio.supports_filtering(extra)
		is_adult = self.is_adult(addon_id, cat_type, cat_id)

		for item in items:
			if supports_filtering:
				menu = self.create_ctx_menu()
				menu.add_menu_item(self._("Advanced filtering"), cmd=self.advanced_filter, addon_id=addon_id, cat_type=cat_type, cat_id=cat_id, extra=extra, update_content=params)
			else:
				menu = {}
			self.add_item_uni(addon_id, item, menu, is_adult)

		if len(items) >= STREMIO_PAGE_SIZE and self.stremio.supports_paging(extra):
			self.add_next(cmd=self.list_catalog, addon_id=addon_id, cat_type=cat_type, cat_id=cat_id, extra=extra, page=page+1)

	# #################################################################################################

	def get_advanced_filter_params(self, extra):
		cfg = []
		cfg_names = []

		# filter out "garbage" and keep only supported parameters
		extra = list(filter(lambda x: x['name'] not in ('search', 'skip',) and x.get('options'), extra))
		params = []

		if len(extra) == 1 and extra[0].get('optionsLimit', 1) == 1:
			# only one filter - use simple list
			e = extra[0]
			c= [x.capitalize() for x in e.get('options',[])]
			idx = self.get_list_input(c, self._("Select filtering") )
			if idx == -1:
				return None

			params.append( (e['name'], e['options'][idx],) )

		elif len(extra) >= 1:
			# more then one filter available - use simple config dialog
			for e in extra:
				name = e['name']

				cfg_names.append(name)
				if e.get('optionsLimit', 1) == 1:
					c=['']
					c.extend(e.get('options',[]))
					c = [ (x, x.capitalize(),) for x in c]
					cfg.append( SimpleConfigSelection(self._(name.capitalize()), choices=c) )
				else:
					c = [ (x, x.capitalize(),) for x in e.get('options',[])]
					cfg.append( SimpleConfigMultiSelection(self._(name.capitalize()), choices=e.get('options',[])) )


			if self.open_simple_config(cfg, title=self._("Advanced filtering")) != True:
				return None

			for i, name in enumerate(cfg_names):
				v = cfg[i].get_value()
				if v:
					if isinstance(v, list):
						for x in v:
							params.append( (name, x,) )
					else:
						params.append( (name, v,) )

		return params

	# #################################################################################################

	def advanced_search_filter(self, keyword, search_id, update_content=False):
		params = self.get_advanced_filter_params(search_id.get('extra'))
		if params == None:
			return self.reload_screen()

		search_id = search_id.copy()
		search_id['params'] = params

		if update_content:
			self.update_content()

		return self.search(keyword, search_id=search_id)

	# #################################################################################################

	def advanced_filter(self, addon_id, cat_type, cat_id, extra, update_content=False):
		params = self.get_advanced_filter_params(extra)
		if params == None:
			return self.reload_screen()

		if update_content:
			self.update_content()

		return self.list_catalog(addon_id, cat_type, cat_id, params=params, extra=extra)

	# #################################################################################################

	def add_item_uni(self, addon_id, item, menu=None, is_adult=False):
		genres = item.get('genres') or item.get('genre')

		if not genres:
			# get genres from links
			genres = [g.get('name') for g in filter(lambda x: (x.get('category') or '').lower() == 'genres', item.get('links') or [])]

		if genres:
			genres = [g.strip().capitalize() for g in genres if g]

		il = InfoLabels(item['name'], auto_genres=True)
		il.year = unicode(item.get('releaseInfo') or item.get('released') or '').split('-')[0].split('–')[0] or None
		il.desc = item.get('description')
		il.genre = genres
		il.rating = item.get('imdbRating')
		il.img = item.get('poster') or item.get('logo')
		il.adult = is_adult or None

		if item.get('trailers'):
			menu = menu or self.create_ctx_menu()
			menu.add_media_menu_item(self._("Play trailer"), cmd=self.resolve_trailer, trailers=item['trailers'])

		if item['type'] in ('movie', 'tv') and not item['id'].startswith(self.collection_prefixes):
			self.add_video(il, menu=menu, cmd=self.resolve_stream, video_title=il.format_title(False), item_type=item['type'], item_id=item['id'], addon_id=addon_id, cached_item_data=il, streams=item.get('streams'), search_query=il.search_query())
		else:
			il.item_type = item['type']
			il.item_id = item['id']
			self.add_dir(il, menu=menu, cmd=self.list_videos, addon_id=addon_id, item_type=item['type'], item_id=item['id'], cached_item_data=il, search_query=il.search_query())

	# #################################################################################################

	def list_videos(self, addon_id, item_type, item_id, cached_item_data=None, search_query=None):
		if addon_id:
			addon = self.stremio.get_addon(addon_id)
			meta = addon.get_meta(item_type, item_id)
		else:
			meta = None

		if meta:
			self.log_debug("Meta resolved using %s" % addon)
		else:
			# addon doesn't support meta - search for any other
			for a in self.stremio.get_meta_addons(item_id):
				meta = a.get_meta(item_type, item_id)

				if meta:
					self.log_debug("Meta resolved using %s" % a)
					addon_id = a.addon_id
					break
			else:
				self.log_error("Can't get more info about series item: %s" % item_id)
				return

		seasons = sorted(set([v.get('season') for v in (meta.get('videos') or [])]))
		meta['adult'] = self.is_adult(addon_id, item_type, item_id)

		if len(seasons) == 1:
			return self.list_meta(addon_id, meta, seasons[0], cached_item_data, search_query)

		for s in seasons:
			if not s or s == 0:
				sname = self._("Special")
			else:
				sname = '{} {}'.format(self._("Season"), s)

			self.add_dir(sname, cmd=self.list_meta, addon_id=addon_id, season=s, meta=meta, cached_item_data=cached_item_data, search_query=search_query)

	# #################################################################################################

	def list_meta(self, addon_id, meta, season=None, cached_item_data=None, search_query=None):
		genres = meta.get('genres') or meta.get('genre')

		if not genres:
			# get genres from links
			genres = [g.get('name','').capitalize() for g in filter(lambda x: (x.get('category') or '').lower() == 'genres', meta.get('links') or []) if g]

		for v in filter(lambda x: x.get('season') == season, (meta.get('videos') or [])):
			name = meta.get('name') or (cached_item_data.title if cached_item_data else '')

			il = InfoLabels(name, auto_genres=True)
			il.desc = v.get('description')
			il.year = unicode(v.get('releaseInfo') or v.get('released') or '').split('-')[0].split('–')[0] or None
			il.genre = genres
			il.episode_name = v.get('name') or v.get('title')
			il.episode_num = v.get('episode')
			il.season_num = season
			il.adult = meta['adult']

			aired = v.get('firstAired') or v.get('released')

			if search_query:
				search_query += il._get_epcode()[1]

			if aired:
				aired = iso8601_to_datetime(aired)
				il.active = aired < datetime.now()

			il.img = v.get('poster') or v.get('thumbnail') or meta.get('poster') or meta.get('logo')
			if il.active:
				self.add_video(il, cmd=self.resolve_stream, video_title=il.format_title(False), item_type=meta['type'], addon_id=addon_id, item_id=v['id'], cached_item_data=cached_item_data, streams=v.get('streams'), search_query=search_query)
			else:
				self.add_video(il)

	# #################################################################################################

	def filter_streams(self, streams):
		# TODO: filter streams by quality, lang or anything other; try to parse or guess metadata
		for addon_id, slist in streams:
			pass

		return streams

	# #################################################################################################

	def format_stream_title(self, addon, sinfo, idx):
		# TODO: create nice stream title - it is also possible to create custom formating based on addon ID
		if hasattr(addon, 'format_stream_title'):
			try:
				return addon.format_stream_title(sinfo)
			except:
				self.log_exception()

		return (clean_str(sinfo.get('name')) or addon.name, clean_str(sinfo['title'].split('\n', 1)[1] if '\n' in sinfo.get('title','') else sinfo.get('title','') ) or clean_str(sinfo.get('description')) or idx+1,)

	# #################################################################################################

	def resolve_stream(self, video_title, item_type, item_id, addon_id=None, cached_item_data=None, streams=None, search_query=None):
		if self.play_time >= 300:
			self.ensure_supporter(self._("You have reached the limit and playback of another item is not available for you. Unlimited playback is only available for ArchivCZSK supporters."), False)

		if streams:
			if cached_item_data:
				cached_item_data.streams = streams

			streams = [ (addon_id, s,) for s in streams]
		else:
			streams = []

		if item_id.startswith('yt_id:'):
			# check if it's youtube video - this will be handled directly without stream addons
			youtube_params = {
				'url': item_id.split(':')[-1],
				'title': video_title
			}

			return self.call_another_addon('plugin.video.yt', youtube_params, 'resolve')

		enable_adult = self.get_parental_settings('unlocked')
		if addon_id and not streams:
			# addon that provided catalog has priority to resolve streams
			addon = self.stremio.get_addon(addon_id)
			try:
				if enable_adult or not self.is_adult(addon.addon_id):
					for s in (addon.get_streams(item_type, item_id, search_query) or []):
						if s:
							streams.append( (addon, s,) )
			except:
				self.log_error("Failed to resolve stream using addon %s" % addon)
				self.log_exception()


		if not streams:
			lock = threading.Lock()
			def get_streams(a):
				try:
					self.log_debug("Requesting streams from %s" % a)
					ret = a.get_streams(item_type, item_id, search_query) or []

					with lock:
						for s in ret:
							if s:
								streams.append( (a, s,))

					self.log_debug("Received %d streams from %s" % (len(ret), a))
				except:
					self.log_error("Failed to resolve stream using addon %s" % a)
					self.log_exception()

			threads = []
			for a in self.stremio.get_stream_addons(item_id):
				if enable_adult or not self.is_adult(a.addon_id):
					threads.append(threading.Thread(target=get_streams, args=(a,)))

			for t in threads:
				t.start()

			for t in threads:
				t.join()

		if not self.service.is_available():
			# stremio service is not available, so filter out torrents, because they are not playable
			streams = list(filter(lambda x: x[1].get('url') or x[1].get('resolve_cbk'), streams))

		if not streams:
			self.log_error("No stream found for %s %s" % (item_type, item_id))
			raise AddonInfoException(self._("No playable stream found for this item"))

		streams2 = self.filter_streams(streams)

		if not streams2:
			self.log_info("No stream left after filtering - keeping all")
		else:
			streams = streams2

		if len(streams) == 1:
			stream = streams[0][1]
			stream_addon = streams[0][0]
		else:
			titles = []
			for i, s in enumerate(streams):
				titles.append(self.format_stream_title(s[0], s[1], i))

			idx = self.get_list_input(titles, self._("Please select stream"))
			if idx == -1:
				return
			else:
				stream = streams[idx][1]
				stream_addon = streams[idx][0]

		if stream.get('resolve_cbk'):
			try:
				stream['url'] = stream['resolve_cbk']()
			except Exception as e:
				self.log_error("Failed to resolve stream URL using callback")
				self.log_exception()
				raise AddonInfoException(self._("Failed to resolve stream URL") + ':\n%s' % str(e))

			del stream['resolve_cbk']

		self.log_debug("Selected stream from %s: %s" % (stream_addon, json.dumps(stream)))

		data_item = {
			'subs': self.download_subtitles(item_type, item_id, stream.get('behaviorHints')) if self.get_setting('external-subtitles') else None,
			'item_type': item_type,
			'item_id': item_id,
			'cached_item_data': cached_item_data
		}

		settings = {}
		last_position = self.watched.get_last_position(item_id)

		if self.silent_mode == False and self.get_setting('save-last-play-pos') and last_position > 0:
			settings['resume_time_sec'] = last_position

		settings['lang_priority'] = self.dubbed_lang_list
		if 'en' not in settings['lang_priority']:
			settings['lang_fallback'] = ['en']

		settings['subs_autostart'] = self.get_setting('subs-autostart') in ('always', 'undubbed')
		settings['subs_always'] = self.get_setting('subs-autostart') == 'always'
		settings['subs_forced_autostart'] = self.get_setting('forced-subs-autostart')

		if stream.get('extra-headers'):
			settings['extra-headers'] = stream['extra-headers']

		if stream.get('user-agent'):
			settings['user-agent'] = stream['user-agent']

		if stream.get('infoHash'):
			# torrent
			info_hash = stream.get('infoHash')
			file_idx = stream.get('fileIdx', 0)
			trackers = stream.get('sources')
			if self.service.probe(info_hash, file_idx, trackers):
				self.add_play(video_title, self.service.get_stream(info_hash, file_idx, trackers), settings=settings, data_item=data_item)
		else:
			# direct HTTP stream
			url = stream.get('url')
			if urlparse(url).path.endswith('.m3u8'):
				hls_streams = self.resolve_hls_streams(url)
				if hls_streams:
					for s in hls_streams:
						info_labels = {
							'bandwidth': s['bandwidth'],
							'quality': s.get('resolution', 'x???').split('x')[1] + 'p'
						}
						self.add_play(video_title, s['url'], info_labels=info_labels, settings=settings, data_item=data_item)
				else:
					# maybe it is not master playlist, so try to play it directly
					self.add_play(video_title, url, settings=settings, data_item=data_item)
			else:
				self.add_play(video_title, url, settings=settings, data_item=data_item)

	# #################################################################################################

	def get_hls_info(self, stream_key):
		return {
			'url': stream_key['u'],
			'bandwidth': stream_key['b'],
			'headers': stream_key['h']
		}

	# #################################################################################################

	def resolve_hls_streams(self, url, user_agent=None):
		if user_agent:
			headers = {
				'User-Agent': user_agent
			}
		else:
			headers = None

		streams = self.get_hls_streams(url, headers=headers)

		for stream in (streams or []):
			stream['url'] = stream_key_to_hls_url(self.http_endpoint, {'u':stream['playlist_url'], 'b': stream['bandwidth'], 'h': headers})
#			self.log_debug("HLS for bandwidth %s: %s" % (stream['bandwidth'], stream['url']))

		return streams

	# #################################################################################################

	def resolve_trailer(self, trailers):
		playlist = self.add_playlist(self._('Trailers'))

		for i, t in enumerate(trailers):
			if t.get('type') in ('Trailer', 'Clip'):
				youtube_params = {
					'url': t['source'],
					'title': '{} {}'.format(self._("Trailer"), i),
					'playlist': playlist
				}

				self.call_another_addon('plugin.video.yt', youtube_params, 'resolve')

	# #################################################################################################

	def download_subtitles(self, item_type, item_id, hints):
		lang_map = {
			'sk': ('sk', 'slo', 'slk'),
			'cs': ('cs', 'cze', 'ces'),
			'en': ('en', 'eng'),
			'hu': ('hu', 'hun'),
			'de': ('de', 'deu', 'ger'),
			'pl': ('pl', 'pol')
		}
		if not hints:
			return

		subtitles = []
		for a in self.stremio.get_subtitle_addons(item_id):
			subtitles.extend( a.get_subtitles(item_type, item_id, hints.get('filename'), hints.get('videoSize'), hints.get('videoHash')))

		filtered_subtitles = []
		for s in subtitles:
			for l in self.lang_list:
				if s.get('lang') in lang_map.get(l,[]):
					filtered_subtitles.append(s)

		ret = []
		for i, s in enumerate(filtered_subtitles):
			try:
				# TODO: add support for VTT or other types of subtitles
				name = '/tmp/{:02d}_{}.srt'.format(i+1, s['lang'])
				with open(name, 'wb') as f:
					f.write(self.stremio.req_session.get(s['url']).content)

				self.log_debug("Adding subtitle %s to list of downloaded" % name)
				ret.append(name)
			except:
				self.log_exception()

		self.log_info("Found %d subtitles" % len(ret))
		return ret

	# #################################################################################################

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		if not hasattr(self, 'play_start'):
			self.play_start = 0

		if action in ('play', 'unpause'):
			self.play_start = int(time())
		elif action in ('end', 'pause'):
			if self.play_start > 0:
				self.play_time += (int(time()) - self.play_start)
				self.play_start = 0

		if not data_item:
			return

		subs = data_item.get('subs') or []
		item_id = data_item.get('item_id')
		item_type = data_item.get('item_type')
		cached_item_data = data_item.get('cached_item_data')

		if action.lower() == 'play':
			if cached_item_data and hasattr(cached_item_data, 'item_type') and hasattr(cached_item_data, 'item_id'):
				# this part is valid for series and channels - replace episode/video type+id by series/channel type+id
				item_type = cached_item_data.item_type
				item_id = cached_item_data.item_id

			# add to watched all items except for TV channels
			if item_type not in ('tv',):
				self.watched.set(item_type, item_id)
				self.save_cached_item(item_type, item_id, cached_item_data)
		elif action.lower() == 'watching':
			pass

		elif action.lower() == 'end':
			for s in subs:
				self.log_debug("Removing subtitle %s" % s)
				try:
					os.remove(s)
				except:
					pass

			if item_id and position and self.get_setting('save-last-play-pos'):
				if duration and position < (duration * int(self.get_setting('last-play-pos-limit'))) // 100:
					self.watched.set_last_position(item_id, position)
				else:
					# remove saved position from database
					self.watched.set_last_position( item_id, None )

			self.watched.save()
			pass

	# #################################################################################################

	def save_cached_item(self, item_type, item_id, item_data):
		if item_type and item_id:
			cache_name = '{}_{}'.format(item_type, item_id).replace('/', '')
			if item_data == None or not self.load_cached_data(cache_name):
				s = item_data.save(blacklist=['item_type', 'item_id']) if item_data != None else None
#				self.log_debug("Saving cached data: %s" % json.dumps(s))
				self.save_cached_data(cache_name, s)

	# #################################################################################################

	def load_cached_item(self, item_type, item_id):
		cache_name = '{}_{}'.format(item_type, item_id).replace('/', '')
		item_data = self.load_cached_data(cache_name)

		il = InfoLabels(None)
		if 'info_labels' in item_data:
			# backward compatiblity with version <= 1.1
			info = item_data['info_labels']
			il.load({
				'title': info.get('title'),
				'desc': info.get('plot'),
				'year': info.get('year'),
				'img': item_data.get('img'),
				'rating': info.get('rating')
			})
		else:
			il.load(item_data)

		return il

	# #################################################################################################
