# -*- coding: utf-8 -*-
import os
import re
import time
import threading

# urllib helpers (prefer tools_archivczsk.six for py2/py3 compatibility)
try:
	from tools_archivczsk.six.moves.urllib.parse import urlparse, urlunparse, quote, urlencode
except Exception:
	# fallback (should not be needed on normal ArchivCZSK images)
	try:
		from urllib.parse import urlparse, urlunparse, quote, urlencode
	except Exception:
		try:
			from urlparse import urlparse, urlunparse
			from urllib import quote, urlencode
		except Exception:
			urlparse = None
			urlunparse = None
			quote = None
			urlencode = None

from tools_archivczsk.contentprovider.exception import AddonErrorException

try:
	import queue
except Exception:
	try:
		import Queue as queue
	except Exception:
		queue = None

try:
	from requests.auth import HTTPDigestAuth
except Exception:
	HTTPDigestAuth = None

try:
	from PIL import Image
	_PIL_OK = True
except Exception:
	_PIL_OK = False


# ---- PICON refresh ----
_PICON_TTL_DAYS = 7
_PICON_STAMP = "/tmp/archivczsk_tvheadend_img.picon.stamp"

# ---- parallel download ----
_PICON_MAX_WORKERS = 6  # 4-8 je zvyčajne ideál na OpenATV, viac často už nepomôže


class Tvheadend(object):

	# Tvheadend akceptuje ?title=... na /stream/*
	USE_TITLE_PARAM = True

	# u teba funguje /stream/channel/<uuid>
	PREFER_CHANNEL_STREAM = True

	# endpointy (tvoje správanie)
	STREAM_CH_ENDPOINT = 'stream/channel/%s'     # ✅ funguje u teba
	STREAM_CHID_ENDPOINT = 'stream/channelid/%s' # ❌ u teba 400, nechávame len fallback
	STREAM_SVC_ENDPOINT = 'stream/service/%s'    # ✅ funguje, ale UI často bez "Channel"

	def __init__(self, cp):
		self.cp = cp
		self._ = cp._
		self.req = cp.get_requests_session()

		# cache folder na boxe (pre lokálne cache ikon/posterov ak to niekto používa)
		self._img_cache_dir = '/tmp/archivczsk_tvheadend_img'
		try:
			if not os.path.isdir(self._img_cache_dir):
				os.makedirs(self._img_cache_dir)
		except Exception:
			pass

		# ✅ pri štarte boxu/pluginu stiahni imagecache ikonky do /tmp (flat názvy)
		try:
			self._init_picons()
		except Exception:
			pass

	def _timeout(self):
		try:
			t = int(self.cp.get_setting('loading_timeout'))
		except Exception:
			t = 15
		return None if t == 0 else t

	def base_url(self):
		host = (self.cp.get_setting('host') or '').strip()
		if not host:
			raise AddonErrorException(self._("Missing Tvheadend server address in settings."))

		if host.startswith('http://') or host.startswith('https://'):
			u = urlparse(host)
			scheme = u.scheme
			hostname = u.hostname or ''
			port = str(u.port or (9982 if scheme == 'https' else 9981))
			return '%s://%s:%s' % (scheme, hostname, port)

		port = str(self.cp.get_setting('port') or '9981').strip()
		use_https = bool(self.cp.get_setting('use_https'))
		scheme = 'https' if use_https else 'http'
		return '%s://%s:%s' % (scheme, host, port)

	def _apply_auth_to_session(self):
		user = (self.cp.get_setting('username') or '').strip()
		pwd = (self.cp.get_setting('password') or '')
		mode = (self.cp.get_setting('http_auth_mode') or 'auto').strip().lower()

		if not user or mode == 'none':
			self.req.auth = None
			return

		# digest preferované
		if mode in ('digest', 'auto') and HTTPDigestAuth is not None:
			self.req.auth = HTTPDigestAuth(user, pwd)
		else:
			self.req.auth = (user, pwd)

	def _url(self, path):
		path = (path or '').lstrip('/')
		return self.base_url().rstrip('/') + '/' + path

	def api_get(self, path, params=None):
		self._apply_auth_to_session()
		url = self._url(path)
		resp = self.req.get(url, params=params or {}, timeout=self._timeout())
		try:
			resp.raise_for_status()
		except Exception as e:
			raise AddonErrorException('%s\n%s' % (self._("Tvheadend API request failed."), str(e)))

		try:
			return resp.json()
		except Exception:
			raise AddonErrorException(self._("Tvheadend returned invalid JSON."))

	def api_get_all(self, path, params=None, page_limit=500):
		params = dict(params or {})
		start = int(params.get('start') or 0)
		limit = int(params.get('limit') or page_limit)
		if limit <= 0:
			limit = page_limit

		entries = []
		total = None
		for _ in range(0, 200):
			params['start'] = start
			params['limit'] = limit
			data = self.api_get(path, params)
			page = data.get('entries', []) or []
			entries.extend(page)

			if total is None:
				try:
					total = int(data.get('total'))
				except Exception:
					total = None

			if total is not None and len(entries) >= total:
				break
			if not page:
				break
			if len(page) < limit:
				break
			start += limit

		return entries

	# ---------------------------------------------------------------------------------
	# LOGIN helpers
	# ---------------------------------------------------------------------------------

	def is_configured(self):
		host = (self.cp.get_setting('host') or '').strip()
		user = (self.cp.get_setting('username') or '').strip()
		pwd = (self.cp.get_setting('password') or '')
		return bool(host and user and pwd)

	def check_login(self):
		self.api_get('api/serverinfo', params={})
		return True

	# ---------------------------------------------------------------------------------
	# STREAM URL helpers
	# ---------------------------------------------------------------------------------

	def _url_with_creds(self, full_url):
		# creds do URL (niektoré E2 playery nevedia digest)
		user = (self.cp.get_setting('username') or '').strip()
		pwd = (self.cp.get_setting('password') or '')
		if not user:
			return full_url
		u = urlparse(full_url)
		netloc = '%s:%s@%s' % (quote(user, safe=''), quote(pwd, safe=''), u.netloc)
		return urlunparse((u.scheme, netloc, u.path, u.params, u.query, u.fragment))

	def _build_stream_url(self, endpoint_path, profile=None, channel_title=None):
		url = self._url(endpoint_path)
		params = {}
		if profile:
			params['profile'] = profile

		if self.USE_TITLE_PARAM and channel_title:
			try:
				ct = str(channel_title).strip()
				if ct:
					params['title'] = ct
			except Exception:
				pass

		if params:
			url = url + '?' + urlencode(params)

		return self._url_with_creds(url)

	def make_live_stream_url(self, channel_uuid=None, service_uuid=None, channel_title=None):
		"""
		Tvoj Tvheadend:
		- ✅ /stream/channel/<uuid> = funguje a vypĺňa "Channel" v TVH UI
		- ❌ /stream/channelid/<uuid> = 400
		- ✅ /stream/service/<uuid> = funguje, ale často bez "Channel"
		"""
		profile = (self.cp.get_setting('profile') or 'pass').strip()

		# 1) preferuj CHANNEL stream
		if self.PREFER_CHANNEL_STREAM and channel_uuid:
			return self._build_stream_url(
				self.STREAM_CH_ENDPOINT % channel_uuid,
				profile=profile,
				channel_title=channel_title
			)

		# 2) service stream (fallback)
		if service_uuid:
			return self._build_stream_url(
				self.STREAM_SVC_ENDPOINT % service_uuid,
				profile=profile,
				channel_title=channel_title
			)

		# 3) channelid (posledná šanca)
		if channel_uuid:
			return self._build_stream_url(
				self.STREAM_CHID_ENDPOINT % channel_uuid,
				profile=profile,
				channel_title=channel_title
			)

		raise AddonErrorException(self._("Missing channel/service identifier for streaming."))

	def make_dvr_url(self, entry_url_field):
		if not entry_url_field:
			return None
		return self._url_with_creds(self._url(entry_url_field))

	# ---------------------------------------------------------------------------------
	# ICON helpers (PNG cache pre UI)
	# ---------------------------------------------------------------------------------

	def _sanitize_filename(self, s):
		s = s or ''
		s = re.sub(r'[^a-zA-Z0-9_.-]+', '_', s)
		return s[:80] if len(s) > 80 else s

	def _cache_path_for_icon(self, icon_public_url):
		key = self._sanitize_filename((icon_public_url or '').replace('/', '_'))
		if not key:
			key = 'img'
		return os.path.join(self._img_cache_dir, '%s.png' % key)

	# ---------------------------------------------------------------------------------
	# ✅ imagecache -> flat filename helper
	# ---------------------------------------------------------------------------------

	def _strip_query(self, p):
		try:
			return (p or '').split('?', 1)[0]
		except Exception:
			return p

	def _flat_imagecache_filename(self, icon_public_url):
		"""
		imagecache/1024 -> imagecache_1024.png (bez podpriečinka)
		"""
		ipu = (icon_public_url or '').strip()
		if not ipu:
			return None
		ipu = self._strip_query(ipu).lstrip('/')

		if not ipu.startswith('imagecache/'):
			return None

		idpart = ipu.split('/', 1)[1].strip()
		if not idpart:
			return None

		# odstráň príponu ak už bola (png/jpg/jpeg)
		idlower = idpart.lower()
		for ext in ('.png', '.jpg', '.jpeg'):
			if idlower.endswith(ext):
				idpart = idpart[: -len(ext)]
				break

		idpart = self._sanitize_filename(idpart)
		if not idpart:
			return None

		return "imagecache_%s.png" % idpart

	def _picon_local_path_from_icon_public_url(self, icon_public_url):
		"""
		✅ imagecache/<id> -> /tmp/archivczsk_tvheadend_img/imagecache_<id>.png
		ostatné fallback na pôvodnú cache logiku
		"""
		fn = self._flat_imagecache_filename(icon_public_url)
		if fn:
			return os.path.join(self._img_cache_dir, fn)
		return self._cache_path_for_icon(icon_public_url)

	# ---------------------------------------------------------------------------------
	# ✅ Auto-download imagecache ikoniek pri štarte (7 dní) + PARALELNE
	# ---------------------------------------------------------------------------------

	def _init_picons(self):
		now = int(time.time())
		ttl = int(_PICON_TTL_DAYS) * 24 * 3600

		last = 0
		try:
			last = int(os.path.getmtime(_PICON_STAMP))
		except Exception:
			last = 0

		if last and (now - last) < ttl:
			return

		try:
			if not os.path.isdir(self._img_cache_dir):
				os.makedirs(self._img_cache_dir)
		except Exception:
			pass

		try:
			channels = self.get_channels()
		except Exception:
			channels = []

		# priprav joby
		jobs = []
		for ch in channels:
			icon = ch.get('icon_public_url')
			if not icon:
				continue

			# len imagecache veci (aby sme teraz nerobili bordel)
			if not (icon.lstrip('/').startswith('imagecache/')):
				continue

			dst = self._picon_local_path_from_icon_public_url(icon)
			if not dst:
				continue

			try:
				if os.path.isfile(dst) and os.path.getsize(dst) > 0:
					continue
			except Exception:
				pass

			jobs.append((icon, dst))

		# nič netreba robiť
		if not jobs:
			try:
				with open(_PICON_STAMP, 'w') as f:
					f.write(str(now))
			except Exception:
				pass
			return

		# fallback: bez queue -> sekvenčne
		if queue is None:
			for icon, dst in jobs:
				try:
					self.download_image_to_file(icon, dst)
				except Exception:
					pass
			try:
				with open(_PICON_STAMP, 'w') as f:
					f.write(str(now))
			except Exception:
				pass
			return

		q = queue.Queue()
		for it in jobs:
			q.put(it)

		workers = int(_PICON_MAX_WORKERS)
		if workers < 1:
			workers = 1
		if workers > 12:
			workers = 12
		if workers > len(jobs):
			workers = len(jobs)

		def _make_session():
			# vlastná session pre každý thread (rýchle + bezpečnejšie než zdieľať self.req)
			s = self.cp.get_requests_session()

			user = (self.cp.get_setting('username') or '').strip()
			pwd = (self.cp.get_setting('password') or '')
			mode = (self.cp.get_setting('http_auth_mode') or 'auto').strip().lower()

			if not user or mode == 'none':
				s.auth = None
			else:
				if mode in ('digest', 'auto') and HTTPDigestAuth is not None:
					s.auth = HTTPDigestAuth(user, pwd)
				else:
					s.auth = (user, pwd)
			return s

		def worker():
			sess = _make_session()
			while True:
				try:
					icon, dst = q.get_nowait()
				except Exception:
					return
				try:
					self.download_image_to_file(icon, dst, session=sess)
				except Exception:
					pass
				finally:
					try:
						q.task_done()
					except Exception:
						pass

		for _ in range(workers):
			t = threading.Thread(target=worker)
			t.daemon = True
			t.start()

		try:
			q.join()
		except Exception:
			pass

		# stamp
		try:
			with open(_PICON_STAMP, 'w') as f:
				f.write(str(now))
		except Exception:
			pass

	def make_icon_url(self, icon_public_url):
		"""
		Stiahne imagecache do lokálneho /tmp cache a vráti cestu k súboru.
		Toto je OK na poster/ikonku v addon UI.

		✅ Ak je to imagecache/*, preferuje už stiahnutý flat súbor imagecache_<id>.png
		"""
		if not icon_public_url:
			return None

		if icon_public_url.startswith('file://'):
			return icon_public_url.replace('file://', '')

		if icon_public_url.startswith('http://') or icon_public_url.startswith('https://'):
			return icon_public_url

		if icon_public_url.startswith('picon://'):
			return icon_public_url

		# ✅ preferuj imagecache flat lokálny súbor
		try:
			dst2 = self._picon_local_path_from_icon_public_url(icon_public_url)
			if dst2 and os.path.isfile(dst2) and os.path.getsize(dst2) > 0:
				return dst2
		except Exception:
			pass

		url = self._url(icon_public_url)
		dst = self._cache_path_for_icon(icon_public_url)

		try:
			if os.path.isfile(dst) and os.path.getsize(dst) > 0:
				return dst
		except Exception:
			pass

		try:
			self._apply_auth_to_session()
			r = self.req.get(url, timeout=self._timeout(), stream=True)
			if r.status_code != 200:
				return None

			ctype = (r.headers.get('Content-Type') or '').lower()
			if ctype and not ctype.startswith('image/'):
				return None

			with open(dst, 'wb') as f:
				for chunk in r.iter_content(chunk_size=8192):
					if chunk:
						f.write(chunk)

			try:
				if os.path.getsize(dst) > 0:
					return dst
			except Exception:
				pass
		except Exception:
			return None

		return None

	def make_icon_http_url(self, icon_public_url):
		"""
		✅ Vráti absolútny HTTP(S) URL na icon_public_url (typicky imagecache/XXXX).
		"""
		if not icon_public_url:
			return None

		if icon_public_url.startswith('file://'):
			return None

		if icon_public_url.startswith('http://') or icon_public_url.startswith('https://'):
			return self._url_with_creds(icon_public_url)

		if icon_public_url.startswith('picon://'):
			return icon_public_url

		return self._url_with_creds(self._url(icon_public_url))

	# ---------------------------------------------------------------------------------
	# ✅ PICON downloader helper (digest) – uloží výsledok do dst_path
	# ---------------------------------------------------------------------------------

	def _candidate_image_paths(self, icon_public_url):
		ipu = (icon_public_url or '').strip()
		if not ipu:
			return []

		# normalizuj
		ipu = ipu.lstrip('/')

		cands = [ipu]

		# Ak TVH vracia "imagecache/1643", veľa buildov potrebuje príponu
		if ipu.startswith('imagecache/'):
			idpart = ipu.split('/', 1)[1].strip()
			if idpart:
				cands.append('imagecache/%s.png' % idpart)
				cands.append('imagecache/%s.jpg' % idpart)
				cands.append('imagecache/%s.jpeg' % idpart)

		# niekedy je to "imagecache/1643?something" – nechaj aj bez query
		if '?' in ipu:
			cands.append(ipu.split('?', 1)[0])

		# unikátne, v poradí
		out = []
		seen = set()
		for p in cands:
			if p and p not in seen:
				seen.add(p)
				out.append(p)
		return out

	def download_image_to_file(self, icon_public_url, dst_path, session=None):
		"""
		Stiahne obrázok z TVH (digest/basic podľa settings) a uloží do dst_path.
		Pokúsi sa aj o konverziu do PNG ak je PIL dostupný.
		"""
		if not icon_public_url or not dst_path:
			raise AddonErrorException("Missing icon_public_url/dst_path")

		# session (kvôli paralelnému sťahovaniu)
		sess = session if session is not None else self.req

		# ak nepoužívame vlastnú session, uplatni auth do self.req
		if session is None:
			self._apply_auth_to_session()

		dst_dir = os.path.dirname(dst_path)
		try:
			if dst_dir and not os.path.isdir(dst_dir):
				os.makedirs(dst_dir)
		except Exception:
			pass

		last_err = None
		for rel in self._candidate_image_paths(icon_public_url):
			url = self._url(rel)

			try:
				r = sess.get(url, timeout=self._timeout(), stream=True)
			except Exception as e:
				last_err = e
				continue

			if r.status_code != 200:
				last_err = Exception("HTTP %s for %s" % (r.status_code, url))
				continue

			ctype = (r.headers.get('Content-Type') or '').lower()
			if ctype and not ctype.startswith('image/'):
				last_err = Exception("Not an image: %s" % ctype)
				continue

			tmp = dst_path + ".tmp"
			try:
				with open(tmp, 'wb') as f:
					for chunk in r.iter_content(chunk_size=8192):
						if chunk:
							f.write(chunk)
			except Exception as e:
				last_err = e
				try:
					if os.path.exists(tmp):
						os.remove(tmp)
				except Exception:
					pass
				continue

			# ak cieľ je .png a prišlo jpeg a PIL je dostupný -> prekonvertuj
			try:
				if dst_path.lower().endswith(".png") and _PIL_OK:
					try:
						img = Image.open(tmp)
						img = img.convert("RGBA") if img.mode not in ("RGB", "RGBA") else img
						img.save(dst_path, format="PNG")
						try:
							os.remove(tmp)
						except Exception:
							pass
						return True
					except Exception:
						# fallback: nechaj raw bytes
						pass

				# presuň raw
				try:
					if os.path.exists(dst_path):
						os.remove(dst_path)
				except Exception:
					pass
				os.rename(tmp, dst_path)
				return True
			except Exception as e:
				last_err = e
				try:
					if os.path.exists(tmp):
						os.remove(tmp)
				except Exception:
					pass
				continue

		raise AddonErrorException("Image download failed: %s" % (str(last_err) if last_err else "unknown"))

	# ---------------------------------------------------------------------------------
	# API wrappers
	# ---------------------------------------------------------------------------------

	def get_tags(self):
		return self.api_get_all('api/channeltag/grid', {'start': 0}, page_limit=200)

	def get_channels(self):
		return self.api_get_all('api/channel/grid', {'start': 0}, page_limit=1000)

	def get_channels_by_tag(self, tag_uuid):
		channels = self.get_channels()
		if not tag_uuid:
			return channels
		out = []
		for ch in channels:
			tags = ch.get('tags') or []
			if tag_uuid in tags:
				out.append(ch)
		return out

	def get_dvr_finished(self):
		return self.api_get_all('api/dvr/entry/grid_finished', {'start': 0}, page_limit=500)

	# ---------------------------------------------------------------------------------
	# ✅ EPG helpers
	# ---------------------------------------------------------------------------------

	def get_epg_now(self, limit=5000):
		try:
			data = self.api_get("api/epg/events/grid", params={"mode": "now", "limit": int(limit)})
		except Exception:
			return {}
		entries = data.get("entries") or []
		out = {}
		for e in entries:
			ch = e.get("channelUuid")
			if ch:
				out[ch] = e
		return out

	def get_epg_now_next(self, channel_uuid):
		if not channel_uuid:
			return (None, None)

		def _fetch(mode):
			params = {'mode': mode, 'limit': 1, 'start': 0, 'channel': channel_uuid}
			data = self.api_get('api/epg/events/grid', params=params) or {}
			entries = data.get('entries') if isinstance(data, dict) else None
			if entries:
				return entries[0]

			# fallback na iný názov parametra
			params.pop('channel', None)
			params['channelUuid'] = channel_uuid
			data = self.api_get('api/epg/events/grid', params=params) or {}
			entries = data.get('entries') if isinstance(data, dict) else None
			return entries[0] if entries else None

		now_event = None
		next_event = None
		try:
			now_event = _fetch('now')
		except Exception:
			now_event = None
		try:
			next_event = _fetch('next')
		except Exception:
			next_event = None

		return (now_event, next_event)

	# ---------------------------------------------------------------------------------
	# helper: názov kanála podľa service_uuid
	# ---------------------------------------------------------------------------------

	def get_channel_name_by_service_uuid(self, service_uuid):
		if not service_uuid:
			return None
		try:
			channels = self.get_channels()
			for ch in channels:
				services = ch.get('services') or []
				if service_uuid in services:
					return ch.get('name') or None
		except Exception:
			return None
		return None
