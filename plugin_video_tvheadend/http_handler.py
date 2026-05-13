# -*- coding: utf-8 -*-
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler


class TvheadendHTTPRequestHandler(AddonHttpRequestHandler):
	playlive_uri = "/tvheadend/playlive/"

	def __init__(self, content_provider, addon):
		AddonHttpRequestHandler.__init__(self, addon)
		self.cp = content_provider

	def P_playlive(self, request, path):
		if path.startswith("/"):
			path = path[1:]
		key = (path or "").strip()
		if not key:
			return self.reply_error404(request)
		try:
			# FIX 0.48: nevolaj plné self.cp.login() — get_url_by_channel_key()
			# si interne spraví fast-path login cez TTL cache.
			# Pôvodné volanie login(silent=True) pri každom playback-u robilo
			# zbytočný cleanup/init/refresh chain.
			url = self.cp.get_url_by_channel_key(key)
		except Exception:
			url = ""
		if not url:
			return self.reply_error404(request)
		return self.reply_redirect(request, url)
