# -*- coding: utf-8 -*-

import base64
import json
from time import time

from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler

# adresa manifestu nesie token relacie v ceste; obnovujeme ju skor, nez vyprsi
STREAM_TTL = 180


# #################################################################################################
# HTTP handler pre Canal+.
#
# P_dash obsluhuje prehravanie z menu doplnku, P_playlive kanaly z userbouquetu.
# Licencia Canal+ nie je obycajne POST na jednu adresu, ale GetLicence s obalom
# (LiveToken, EpgId, challenge) - preto si prepisujeme get_drm_license.
# #################################################################################################


class CanalplusHTTPRequestHandler(DashHTTPRequestHandler, PlayliveTVHTTPRequestHandler):
	def __init__(self, content_provider, addon):
		super(CanalplusHTTPRequestHandler, self).__init__(content_provider, addon)
		self.dash_proxy_segments = False
		self.dash_internal_decrypt = True
		# platnost adresy manifestu si strazime sami (spolocna pamat ju pri pouziti predlzuje)
		self.cache_life = 900

	# #################################################################################################

	def sync_stream_headers(self):
		"""Segmenty idu cez req_session, potrebuju rovnake hlavicky ako manifest."""
		try:
			self.req_session.headers.update(self.cp.stream_headers())
		except Exception:
			self.cp.log_exception()

	# #################################################################################################

	def P_dash(self, request, path):
		self.sync_stream_headers()
		return super(CanalplusHTTPRequestHandler, self).P_dash(request, path)

	# #################################################################################################

	def get_drm_license(self, drm_info, lic_request):
		"""Canal+ licencia cez GetLicence. Pri inych doplnkoch/typoch sa sprava ako povodna."""
		ctx = drm_info.get('canalplus')
		if not ctx:
			return super(CanalplusHTTPRequestHandler, self).get_drm_license(drm_info, lic_request)

		try:
			return self.cp.api.get_license(ctx, lic_request)
		except Exception:
			self.cp.log_exception()
			return None

	# #################################################################################################

	@staticmethod
	def encode_stream_info(stream_info):
		data = '{' + json.dumps(stream_info) + '}'
		return base64.b64encode(data.encode('utf-8')).decode('utf-8')

	# #################################################################################################

	def get_stream_info_by_channel_key(self, channel_key):
		try:
			stream = self.cp.get_stream_info(channel_key)
		except Exception:
			self.cp.log_exception()
			return None

		if not stream.get('url'):
			return None

		bandwidth = 1000000000
		try:
			streams = self.cp.resolve_streams_for_channel(stream['url'])
			if streams:
				bandwidth = int(streams[0]['bandwidth'])
		except Exception:
			self.cp.log_exception()

		return {
			'url': stream['url'],
			'bandwidth': bandwidth,
			'license': stream.get('license') or {},
			'web': self.cp.api.web_url(),
			'created': int(time()),
		}

	# #################################################################################################

	def P_playlive(self, request, path):
		"""Kanal spusteny z userbouquetu - cesta nesie zakodovany kluc kanala."""
		if path.endswith('/index.mpd'):
			path = path[:-10]
		elif path.endswith('/index'):
			path = path[:-6]

		try:
			channel_key = self.decode_channel_key(path)
		except Exception:
			return self.reply_error404(request)

		stream_info = self.live_cache_get(channel_key)

		if stream_info and (int(time()) - int(stream_info.get('created') or 0)) > STREAM_TTL:
			stream_info = None

		if not stream_info:
			stream_info = self.get_stream_info_by_channel_key(channel_key)
			if not stream_info:
				return self.reply_error404(request)
			self.live_cache_put(channel_key, stream_info)

		return self.P_dash(request, self.encode_stream_info(stream_info))

	# #################################################################################################

	def handle_mpd_manifest(self, base_url, root, bandwidth, dash_info={}, cache_key=None):
		"""Okrem spoločného spracovania nechá v manifeste len jednu video skupinu.

		Canal+ (ako Skylink, rovnaká CDN) má video rozdelené do viacerých skupín
		(napr. do 720p a samostatné 1080p). Spoločné spracovanie necháva v každej
		skupine jednu reprezentáciu, takže by ich zostalo viac a prehrávač by si mohol
		vybrať nižšiu, než je zvolená.
		"""
		super(CanalplusHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth,
		                                                             dash_info, cache_key)
		try:
			self.keep_single_video_set(root, bandwidth)
		except Exception:
			self.cp.log_exception()

	# #################################################################################################

	@staticmethod
	def keep_single_video_set(root, bandwidth):
		"""Zo všetkých video skupín nechá tú, ktorej reprezentácia najlepšie sedí
		na zvolenú šírku pásma."""
		ns = root.tag[1:root.tag.index('}')] if root.tag.startswith('{') else ''
		ns = '{%s}' % ns if ns else ''

		for e_period in root.findall('%sPeriod' % ns):
			video_sets = []
			for e_set in e_period.findall('%sAdaptationSet' % ns):
				content_type = e_set.get('contentType', '')
				mime_type = e_set.get('mimeType', '') or ''
				if content_type == 'video' or mime_type.startswith('video/'):
					best = 0
					for e_rep in e_set.findall('%sRepresentation' % ns):
						try:
							best = max(best, int(e_rep.get('bandwidth') or 0))
						except Exception:
							pass
					video_sets.append((best, e_set))

			if len(video_sets) < 2:
				continue

			allowed = [v for v in video_sets if v[0] <= bandwidth]
			if allowed:
				chosen = max(allowed, key=lambda v: v[0])[1]
			else:
				chosen = min(video_sets, key=lambda v: v[0])[1]

			for _best, e_set in video_sets:
				if e_set is not chosen:
					e_period.remove(e_set)

	# #################################################################################################

	def default_handler(self, request, path_full):
		data = 'Default Canal+ handler for path: %s' % path_full
		return self.reply_ok(request, data.encode('utf-8'), 'text/plain; charset=UTF-8')
