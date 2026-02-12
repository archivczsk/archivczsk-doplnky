# -*- coding: utf-8 -*-

import os, json, time

class StremioWatched(object):

	# #################################################################################################

	def __init__(self, cp, tapi=None):
		self.cp = cp
		self.need_save = False
		self.tapi = tapi
		self.items = {}
		self.load()
		self.trakt_need_reload = True
		self.trakt_movies = {}
		self.trakt_shows = {}

	# #################################################################################################

	def get_max_items(self):
		try:
			return int(self.cp.get_setting('keep-last-seen'))
		except:
			return 50

	# #################################################################################################

	def clean(self):
		lp = self.items.get('last_played_position')
		max_items = self.get_max_items()
		if lp and len(lp) > max_items:
			# sort last played items by time added and remove oldest over max items
			lp = [ x[0] for x in sorted(lp.items(), key=lambda x:-x[1]['time']) ][max_items:]
			self.need_save = True

		for item_type in self.items:
			if item_type == 'last_played_position':
				continue

			if len(self.items[item_type]) > max_items:
				for x in self.items[item_type][max_items:]:
					self.clean_metadata(item_type, x)

				self.items[item_type] = self.items[item_type][:max_items]
				self.need_save = True

	# #################################################################################################

	def clean_metadata(self, item_type, item_id):
		self.cp.log_info("Removing metadata for %s %s" % (item_type, item_id))
		self.cp.save_cached_item(item_type, item_id, None)

	# #################################################################################################

	def fix_data_types(self):
		# json store all keys as strings and this breaks seasons, so fix it here
		for item in self.items.get('trakt', {}).get('s', []):
			seasons_data = item.get('s', {})
			for season, episodes in seasons_data.items():
				del seasons_data[season]
				seasons_data[int(season)] = episodes

	# #################################################################################################

	def load(self):
		self.items = self.cp.load_cached_data('watched')
		self.clean()
		self.fix_data_types()

		# #################################################################################################

	def save(self):
		if self.need_save:
			self.cp.save_cached_data('watched', self.items)
			self.need_save = False

	# #################################################################################################

	def get(self, item_type):
		return self.items.get(item_type, [])

	# #################################################################################################

	def set(self, item_type, item_id):
		max_items = self.get_max_items()

		if max_items > 0:
			if item_type not in self.items:
				self.items[item_type] = []

			self.remove(item_type, item_id, False)
			self.items[item_type].insert(0, item_id)

			if len(self.items[item_type]) > max_items:
				for x in self.items[item_type][max_items:]:
					self.clean_metadata(item_type, x)

				self.items[item_type] = self.items[item_type][:max_items]

			self.need_save = True

	# #################################################################################################

	def remove(self, item_type, item_id, clean_metadata=True):
		if item_type in self.items:
			type_root = self.items[item_type]
			i = 0
			for i, x in enumerate(type_root):
				if x == item_id:
					del self.items[item_type][i]
					if clean_metadata:
						self.clean_metadata(item_type, item_id)

					self.need_save = True
					break

	# #################################################################################################

	def set_last_position(self, item_id, position):
		if self.get_max_items() > 0:
			if not 'last_played_position' in self.items:
				self.items['last_played_position'] = {}

			lp = self.items['last_played_position']

			if position:
				lp[item_id] = { 'pos': position, 'time': int(time.time()) }
			elif item_id in lp:
				del lp[item_id]

			self.need_save = True
			self.clean()

	# #################################################################################################

	def get_last_position(self, item_id):
		if 'last_played_position' in self.items:
			return self.items['last_played_position'].get(item_id, {}).get('pos', 0)

		return 0

	# #################################################################################################

	def force_reload(self):
		self.trakt_need_reload = True

		if 'trakt' in self.items:
			self.items['trakt']['mm'] = -1
			self.items['trakt']['ms'] = -1

	# #################################################################################################

	def load_trakt_watched(self):
		reload_movies_index = False
		reload_shows_index = False

		try:
			mm, ms = self.tapi.get_watched_modifications()

			if mm and self.items['trakt'].get('mm', -1) < mm:
				self.items['trakt']['m'] = self.tapi.get_watched_movies()
				self.items['trakt']['mm'] = mm
				reload_movies_index = True
				self.need_save = True

			if ms and self.items['trakt'].get('ms', -1) < ms:
				self.items['trakt']['s'] = self.tapi.get_watched_shows()
				self.items['trakt']['ms'] = mm
				reload_shows_index = True
				self.need_save = True

		except:
			self.items['trakt'] = { 'm': [], 's': [] }

		self.trakt_need_reload = False

		if reload_movies_index or len(self.trakt_movies) == 0:
			self.trakt_movies = { 'trakt': {}, 'tvdb': {}, 'tmdb': {}, 'imdb': {} }
			# create search index for movies
			for item in self.items.get('trakt',{}).get('m',[]):
				for id_name in [ 'trakt', 'tvdb', 'tmdb', 'imdb' ]:
					if id_name in item:
						self.trakt_movies[id_name][ str(item[id_name]) ] = item

		if reload_shows_index or len(self.trakt_shows) == 0:
			self.trakt_shows = { 'trakt': {}, 'tvdb': {}, 'tmdb': {}, 'imdb': {} }
			# create search index for shows
			for item in self.items.get('trakt',{}).get('s',[]):
				for id_name in [ 'trakt', 'tvdb', 'tmdb', 'imdb' ]:
					if id_name in item:
						self.trakt_shows[id_name][ str(item[id_name]) ] = item

		self.save()

	# #################################################################################################

	def save_trakt_watched(self):
		pass

	# #################################################################################################

	def is_trakt_watched_movie(self, unique_ids):
		if self.trakt_need_reload and self.tapi and self.tapi.valid():
			self.load_trakt_watched()

		for k, v in unique_ids.items():
			if k in self.trakt_movies:
				if v in self.trakt_movies[k]:
					return True

		return False

	# #################################################################################################

	def is_trakt_watched_show(self, unique_ids, season, episode):
		if self.trakt_need_reload and self.tapi and self.tapi.valid():
			self.load_trakt_watched()

		for k, v in unique_ids.items():
			if k in self.trakt_shows:
				if v in self.trakt_shows[k]:
					if season in self.trakt_shows[k][v]['s']:
						if episode in self.trakt_shows[k][v]['s'][season]:
							return True
					break

		return False

	# #################################################################################################

	def is_trakt_watched_serie(self, unique_ids, seasons_count=-1):
		if self.trakt_need_reload and self.tapi and self.tapi.valid():
			self.load_trakt_watched()

		for k, v in unique_ids.items():
			if k in self.trakt_shows:
				if v in self.trakt_shows[k]:
					if len(self.trakt_shows[k][v]['s']) == seasons_count:
						return True, True
					else:
						return True, False

		return False, False

	# #################################################################################################

	def is_trakt_watched_season(self, unique_ids, season, episodes_count=-1):
		if self.trakt_need_reload and self.tapi and self.tapi.valid():
			self.load_trakt_watched()

		for k, v in unique_ids.items():
			if k in self.trakt_shows:
				if v in self.trakt_shows[k]:
					if season in self.trakt_shows[k][v]['s']:
						if len(self.trakt_shows[k][v]['s'][season]) == episodes_count:
							return True, True
						else:
							return True, False

		return False, False
