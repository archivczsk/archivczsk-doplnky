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
			# Pri požiadavke cez http handler nemusí byť doplnok nikdy otvorený v GUI.
			# Preto spravíme tichý login a až potom vyriešime URL.
			if not self.cp.login(silent=True):
				return self.reply_error404(request)
			url = self.cp.get_url_by_channel_key(key)
		except Exception:
			url = ""

		if not url:
			return self.reply_error404(request)

		return self.reply_redirect(request, url)
