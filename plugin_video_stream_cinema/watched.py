# -*- coding: utf-8 -*-

import os, json, time
from Plugins.Extensions.archivCZSK.engine.client import log


class SCWatched(object):

	# #################################################################################################

	def __init__(self, data_dir, tapi=None, max_items=50):
		self.DEFAULT_VER = 1
		self.max_items = max_items
		self.data_dir = data_dir
		self.watched_file = os.path.join(self.data_dir, "watched.json")
		self.need_save = False
		self.tapi = tapi
		self.items = {}
		self.load()
		self.trakt_need_reload = True
		self.trakt_movies = {}
		self.trakt_shows = {}
		self.items['ver'] = self.DEFAULT_VER

	# #################################################################################################

	def clean(self):
		lp = self.items.get('last_played_position')
		if lp and len(lp) > self.max_items:
			# sort last played items by time added and remove oldest over max items
			lp = [ x[0] for x in sorted(lp.items(), key=lambda x:-x[1]['time']) ][self.max_items:]
			self.need_save = True

		for wtype in self.items:
			if wtype == 'last_played_position' or wtype == 'ver':
				continue

			if len(self.items[wtype]) > self.max_items:
				self.items[wtype] = self.items[wtype][:self.max_items]
				self.need_save = True

	# #################################################################################################

	def load(self):
		try:
			with open(self.watched_file, "r") as f:
				self.items = json.load(f)

			if 'ver' not in self.items:
				ver = 0
			else:
				ver = self.items['ver']

			if ver == 0:
				# history data are not compatible with current version - clean history
				for wtype in list(self.items.keys()):
					if wtype == 'last_played_position' or wtype == 'ver':
						continue

					del self.items[wtype]

			elif ver > self.DEFAULT_VER:
				# version of this file is newer then supported
				self.items = {}

			self.clean()
		except:
			pass

		# #################################################################################################

	def save(self):
		if self.need_save:
			with open(self.watched_file, "w") as f:
				json.dump(self.items, f)

			self.need_save = False

	# #################################################################################################

	def get(self, wtype):
		return self.items.get(wtype, [])

	# #################################################################################################

	def set(self, wtype, data):
		if self.max_items > 0:
			if wtype not in self.items:
				self.items[wtype] = []

			self.remove(wtype, data)
			self.items[wtype].insert(0, data)

			if len(self.items[wtype]) > self.max_items:
				self.items[wtype] = self.items[wtype][:self.max_items]

			self.need_save = True

	# #################################################################################################

	def remove(self, wtype, data):
		if wtype in self.items:
			type_root = self.items[wtype]
			i = 0
			for x in type_root:
				if x == data:
					del self.items[wtype][i]
					self.need_save = True
					break
				i += 1

	# #################################################################################################

	def set_last_position(self, url, position):
		if self.max_items > 0:
			if not 'last_played_position' in self.items:
				self.items['last_played_position'] = {}

			lp = self.items['last_played_position']

			if position:
				lp[url] = { 'pos': position, 'time': int(time.time()) }
			elif url in lp:
				del lp[url]

			self.need_save = True
			self.clean()

	# #################################################################################################

	def get_last_position(self, url):
		if 'last_played_position' in self.items:
			return self.items['last_played_position'].get(url, {}).get('pos', 0)

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
			for item in self.items['trakt']['m']:
				for id_name in [ 'trakt', 'tvdb', 'tmdb', 'imdb' ]:
					if id_name in item:
						self.trakt_movies[id_name][ str(item[id_name]) ] = item

		if reload_shows_index or len(self.trakt_shows) == 0:
			self.trakt_shows = { 'trakt': {}, 'tvdb': {}, 'tmdb': {}, 'imdb': {} }
			# create search index for shows
			for item in self.items['trakt']['s']:
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
