# -*- coding: utf-8 -*-
from .stremio import StremioAddon
from functools import partial

# #################################################################################################

class InternalPrehrajToAddon(StremioAddon):
	manifest = {
		"id": "internal.prehraj.to",
		"version": "1.0.0",
		"name": "[I] Prehraj.to",
		"description": "Internal addon for Prehraj.to service",
		"types": [
			"movie",
			"series",
		],
		"resources": [
			"stream"
		],
	}

	# #################################################################################################

	def __init__(self, cp):
		super(InternalPrehrajToAddon, self).__init__(cp, None, self.manifest)

	# #################################################################################################

	def get_streams(self, item_type, item_id, search_query=None):
		if not search_query or self.cp.get_setting('internal_prehrajto') == False:
			return None

		data = {
			'keyword': search_query,
			'limit': 10,
			'premium_needed': True,
			'resolved_items': [],
		}

		self.cp.call_another_addon('plugin.video.prehrajto', data, 'json')
		ret = []
		for stream in data['resolved_items'][:10]:
			ret.append({
				'title': stream['title'],
				'size': stream['size'],
				'resolve_cbk': partial(self.resolve_stream, stream['resolve_cbk']),
			})

		return ret

	# #################################################################################################

	def resolve_stream(self, upstream_cbk):
		videos, subtitles = upstream_cbk()
		return videos[0]['url'] if videos else None

	# #################################################################################################

	def format_stream_title(self, stream):
		return (self.name, '{} {}'.format(stream['size'], stream['title']),)

# #################################################################################################

class InternalWebshareAddon(StremioAddon):
	manifest = {
		"id": "internal.webshare.cz",
		"version": "1.0.0",
		"name": "[I] Webshare.cz",
		"description": "Internal addon for Webshare.cz service",
		"types": [
			"movie",
			"series",
		],
		"resources": [
			"stream"
		],
	}

	# #################################################################################################

	def __init__(self, cp):
		super(InternalWebshareAddon, self).__init__(cp, None, self.manifest)

	# #################################################################################################

	def get_streams(self, item_type, item_id, search_query=None):
		if not search_query or self.cp.get_setting('internal_webshare') == False:
			return None

		data = {
			'keyword': search_query,
			'limit': 10,
			'premium_needed': True,
			'resolved_items': [],
		}

		self.cp.call_another_addon('plugin.video.webshare', data, 'json')
		ret = []
		for stream in data['resolved_items'][:10]:
			ret.append({
				'title': stream['title'],
				'size': stream['size'],
				'size_str': stream['size_str'],
				'resolve_cbk': stream['resolve_cbk'],
			})

		return ret

	# #################################################################################################

	def format_stream_title(self, stream):
		return (self.name, '{} {}'.format(stream['size_str'], stream['title']),)

# #################################################################################################

class InternalSkTOnlineAddon(StremioAddon):
	manifest = {
		"id": "internal.sktonline.cz",
		"version": "1.0.0",
		"name": "[I] SkTOnline",
		"description": "Internal addon for SkTOnline service",
		"types": [
			"movie",
			"series",
		],
		"resources": [
			"stream"
		],
	}

	# #################################################################################################

	def __init__(self, cp):
		super(InternalSkTOnlineAddon, self).__init__(cp, None, self.manifest)

	# #################################################################################################

	def get_streams(self, item_type, item_id, search_query=None):
		if not search_query or self.cp.get_setting('internal_sktonline') == False:
			return None

		# remove year from search query to improve search results
		try:
			parts = search_query.split(' ')
			if parts[-1].isdigit() and len(parts[-1]) == 4:
				search_query = ' '.join(parts[:-1])
			elif parts[-2].isdigit() and len(parts[-2]) == 4:
				search_query = ' '.join(parts[:-2] + parts[-1:])
		except:
			pass

		data = {
			'keyword': search_query,
			'limit': 10,
			'resolved_items': [],
		}

		self.cp.call_another_addon('plugin.video.sktonline', data, 'json')
		ret = []
		for stream in data['resolved_items'][:10]:
			ret.append({
				'title': stream['title'],
				'resolve_cbk': partial(self.resolve_stream, stream['resolve_cbk']),
				'extra-headers': {
					'Referer': 'https://online.sktorrent.eu/',
				}
			})

		return ret

	# #################################################################################################

	def resolve_stream(self, upstream_cbk):
		for link in sorted(upstream_cbk(), key=lambda x: int(x[1]), reverse=True):
			return link[0]

		return None

	# #################################################################################################

	def format_stream_title(self, stream):
		return (self.name, stream['title'],)

# #################################################################################################

class InternalCatalogAddon(StremioAddon):
	def __init__(self, cp):
		super(InternalCatalogAddon, self).__init__(cp, self.TRANSPORT_URL)

	def supports_catalog(self, cat_type=None):
		if self.cp.get_setting(self.ENABLED_SETTING_NAME) == False:
			return False

		return super(InternalCatalogAddon, self).supports_catalog(cat_type)

# #################################################################################################

class InternalCZDabingAddon(InternalCatalogAddon):
	TRANSPORT_URL = 'https://katalog.streamstr.stream/manifest.json'
	ENABLED_SETTING_NAME = 'internal_czdabing'

class InternalCinemetaAddon(InternalCatalogAddon):
	TRANSPORT_URL = 'https://v3-cinemeta.strem.io/manifest.json'
	ENABLED_SETTING_NAME = 'internal_cinemeta'

# #################################################################################################

internal_addons_list = [ InternalPrehrajToAddon, InternalWebshareAddon, InternalSkTOnlineAddon, InternalCinemetaAddon, InternalCZDabingAddon ]
