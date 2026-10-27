# -*- coding: utf-8 -*-

import base64
import json
from time import time

from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler

# adresa manifestu nesie token s platnosťou asi 5 minút, obnovujeme ju skôr
STREAM_TTL = 180

# #################################################################################################
# HTTP handler pre Skylink.
#
# P_dash obsluhuje prehrávanie z menu doplnku, P_playlive kanály z userbouquetu -
# z kľúča kanála si vypýta čerstvú adresu manifestu a prepošle ju DASH handleru.
# Licenčnú požiadavku rieši spoločná implementácia, adresa aj hlavičky prichádzajú
# z get_dash_info() v provideri.
# #################################################################################################


class SkylinkHTTPRequestHandler(DashHTTPRequestHandler, PlayliveTVHTTPRequestHandler):
	def __init__(self, content_provider, addon):
		super(SkylinkHTTPRequestHandler, self).__init__(content_provider, addon)
		self.dash_proxy_segments = False
		self.dash_internal_decrypt = True
		# pamäť na adresu manifestu; platnosť si strážime sami, lebo spoločná pamäť
		# predlžuje životnosť pri každom použití a token v adrese by medzitým vypršal
		self.cache_life = 900

	# #################################################################################################

	def sync_stream_headers(self):
		"""Segmenty idú cez req_session, takže potrebuje rovnaké hlavičky ako manifest.

		Nastavujú sa pri každej požiadavke, nie raz v konštruktore - handler vzniká
		ešte pred prihlásením, takže v tej chvíli nie je známa zvolená značka.
		"""
		try:
			self.req_session.headers.update(self.cp.stream_headers())
		except Exception:
			self.cp.log_exception()

	# #################################################################################################

	def P_dash(self, request, path):
		self.sync_stream_headers()
		return super(SkylinkHTTPRequestHandler, self).P_dash(request, path)

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

		max_bitrate = self.cp.get_setting('max_bitrate')
		try:
			max_bitrate = int(max_bitrate)
		except Exception:
			max_bitrate = 0
		max_bitrate = max_bitrate * 1000000 if max_bitrate > 0 else 1000000000

		# vyber reprezentáciu podľa nastaveného rozlíšenia
		bandwidth = max_bitrate
		try:
			streams = self.cp.resolve_streams_for_channel(stream['url'])
			if streams:
				bandwidth = int(streams[0]['bandwidth'])
		except Exception:
			self.cp.log_exception()

		return {
			'url': stream['url'],
			'bandwidth': bandwidth,
			'license_url': stream.get('license_url', ''),
			'privacy_mode': bool(self.cp.get_setting('privacy_mode')),
			'web': self.cp.api.web_url(),
			'created': int(time()),
		}

	# #################################################################################################

	def P_playlive(self, request, path):
		"""Kanál spustený z userbouquetu - cesta nesie zakódovaný kľúč kanála."""
		if path.endswith('/index.mpd'):
			path = path[:-10]
		elif path.endswith('/index'):
			path = path[:-6]

		try:
			channel_key = self.decode_channel_key(path)
		except Exception:
			return self.reply_error404(request)

		stream_info = self.live_cache_get(channel_key)

		# token v adrese manifestu platí asi 5 minút, potom treba novú adresu
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

		Skylink má video rozdelené do dvoch skupín - jedna má rozlíšenia do 720p
		a druhá samotné 1080p. Spoločné spracovanie necháva v každej skupine jednu
		reprezentáciu, takže by v manifeste zostali dve a prehrávač by si mohol
		vybrať vyššiu než nastavenú.
		"""
		super(SkylinkHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth,
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

			# najbližšia nižšia alebo rovná zvolenej šírke pásma, inak najnižšia
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
		data = 'Default Skylink handler for path: %s' % path_full
		return self.reply_ok(request, data.encode('utf-8'), 'text/plain; charset=UTF-8')
