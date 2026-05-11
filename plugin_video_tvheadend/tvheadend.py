# -*- coding: utf-8 -*-
"""
Tvheadend HTTP API klient.

Kompatibilita: Python 2.7 + Python 3.x
- urllib parse importy cez tools_archivczsk.six (preferované) alebo priame fallbacky
- queue/Queue compat
- threading je stdlib, dostupné všade
"""

import os
import re
import time
import threading

# --------------------------------------------------------------------------
# urllib compat (py2/py3)
# --------------------------------------------------------------------------
try:
	from tools_archivczsk.six.moves.urllib.parse import urlparse, urlunparse, quote, urlencode
except Exception:
	try:
		from urllib.parse import urlparse, urlunparse, quote, urlencode
	except ImportError:
		from urlparse import urlparse, urlunparse
		from urllib import quote, urlencode

# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------
try:
	from tools_archivczsk.cache import ExpiringLRUCache
except Exception:
	ExpiringLRUCache = None

# --------------------------------------------------------------------------
# queue compat
# --------------------------------------------------------------------------
try:
	import queue as _queue_mod
except ImportError:
	try:
		import Queue as _queue_mod
	except ImportError:
		_queue_mod = None

# --------------------------------------------------------------------------
# requests extras
# --------------------------------------------------------------------------
try:
	from requests.auth import HTTPDigestAuth
except Exception:
	HTTPDigestAuth = None

# PIL je voliteľný – používa sa len na konverziu ikon
try:
	from PIL import Image as _PIL_Image
	_PIL_OK = True
except Exception:
	_PIL_OK = False

from tools_archivczsk.contentprovider.exception import AddonErrorException


# --------------------------------------------------------------------------
# Konštanty
# --------------------------------------------------------------------------
_PICON_TTL_DAYS = 7
_PICON_STAMP = "/tmp/archivczsk_tvheadend_img.picon.stamp"
_PICON_MAX_WORKERS = 6
_picon_worker_lock = threading.Lock()

# threading.Event – signalizuje že picon worker dobehol
# bouquet._post() čaká na tento event namiesto sleep slučky
_picon_ready_event = threading.Event()


class Tvheadend(object):
	"""
	Thin wrapper nad Tvheadend HTTP API (port 9981/9982).

	Nevyužíva HTSP – všetko ide cez REST JSON API.
	"""

	PREFER_CHANNEL_STREAM = True
	USE_TITLE_PARAM = True

	STREAM_CH_ENDPOINT  = 'stream/channel/%s'
	STREAM_CHID_ENDPOINT = 'stream/channelid/%s'
	STREAM_SVC_ENDPOINT  = 'stream/service/%s'

	# Cache pre kanály s TTL 60 sekúnd
	_channels_cache = ExpiringLRUCache(1, default_timeout=60) if ExpiringLRUCache else None

	def __init__(self, cp):
		self.cp = cp
		self._ = cp._
		self.req = cp.get_requests_session()
		self._img_cache_dir = '/tmp/archivczsk_tvheadend_img'
		try:
			if not os.path.isdir(self._img_cache_dir):
				os.makedirs(self._img_cache_dir)
		except Exception:
			pass
		# picon inicializácia sa spúšťa lazily – nie v __init__ aby neblokovala GUI

	# ------------------------------------------------------------------
	# Helpers
	# ------------------------------------------------------------------

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

	def _apply_auth_to_session(self, sess=None):
		"""Nastaví autentifikáciu na session (default self.req)."""
		if sess is None:
			sess = self.req
		user = (self.cp.get_setting('username') or '').strip()
		pwd  = (self.cp.get_setting('password') or '')
		mode = (self.cp.get_setting('http_auth_mode') or 'auto').strip().lower()

		if not user or mode == 'none':
			sess.auth = None
			return
		if mode in ('digest', 'auto') and HTTPDigestAuth is not None:
			sess.auth = HTTPDigestAuth(user, pwd)
		else:
			sess.auth = (user, pwd)

	def _url(self, path):
		path = (path or '').lstrip('/')
		return self.base_url().rstrip('/') + '/' + path

	# ------------------------------------------------------------------
	# API volania
	# ------------------------------------------------------------------

	def api_get(self, path, params=None):
		self._apply_auth_to_session()
		url = self._url(path)
		try:
			resp = self.req.get(url, params=params or {}, timeout=self._timeout())
			resp.raise_for_status()
		except AddonErrorException:
			raise
		except Exception as e:
			raise AddonErrorException('%s\n%s' % (self._("Tvheadend API request failed."), str(e)))
		try:
			return resp.json()
		except Exception:
			raise AddonErrorException(self._("Tvheadend returned invalid JSON."))

	def api_get_all(self, path, params=None, page_limit=500):
		"""Automatické stránkovanie – vracia všetky záznamy."""
		params = dict(params or {})
		start  = int(params.get('start', 0))
		limit  = int(params.get('limit', page_limit)) or page_limit

		entries = []
		total   = None
		for _ in range(200):
			params['start'] = start
			params['limit'] = limit
			data = self.api_get(path, params)
			page = data.get('entries') or []
			entries.extend(page)

			if total is None:
				try:
					total = int(data.get('total'))
				except Exception:
					total = None

			if total is not None and len(entries) >= total:
				break
			if not page or len(page) < limit:
				break
			start += limit

		return entries

	# ------------------------------------------------------------------
	# Login
	# ------------------------------------------------------------------

	def is_configured(self):
		host = (self.cp.get_setting('host') or '').strip()
		user = (self.cp.get_setting('username') or '').strip()
		pwd  = (self.cp.get_setting('password') or '')
		return bool(host and user and pwd)

	def check_login(self):
		"""Overí spojenie volaním /api/serverinfo. Vyhodí výnimku pri chybe."""
		self.api_get('api/serverinfo', params={})
		return True

	# ------------------------------------------------------------------
	# Stream URL
	# ------------------------------------------------------------------

	def _url_with_creds(self, full_url):
		user = (self.cp.get_setting('username') or '').strip()
		pwd  = (self.cp.get_setting('password') or '')
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
		profile = (self.cp.get_setting('profile') or 'pass').strip()

		if self.PREFER_CHANNEL_STREAM and channel_uuid:
			return self._build_stream_url(
				self.STREAM_CH_ENDPOINT % channel_uuid,
				profile=profile, channel_title=channel_title
			)
		if service_uuid:
			return self._build_stream_url(
				self.STREAM_SVC_ENDPOINT % service_uuid,
				profile=profile, channel_title=channel_title
			)
		if channel_uuid:
			return self._build_stream_url(
				self.STREAM_CHID_ENDPOINT % channel_uuid,
				profile=profile, channel_title=channel_title
			)
		raise AddonErrorException(self._("Missing channel/service identifier for streaming."))

	def make_dvr_url(self, entry_url_field):
		if not entry_url_field:
			return None
		return self._url_with_creds(self._url(entry_url_field))

	# ------------------------------------------------------------------
	# Icon / picon helpers
	# ------------------------------------------------------------------

	def _sanitize_filename(self, s):
		s = s or ''
		s = re.sub(r'[^a-zA-Z0-9_.-]+', '_', s)
		return s[:80]

	def _strip_query(self, p):
		try:
			return (p or '').split('?', 1)[0]
		except Exception:
			return p or ''

	def _imagecache_id(self, icon_public_url):
		"""Vráti čistý ID z imagecache/ID (bez prípony), alebo None."""
		ipu = (icon_public_url or '').strip().lstrip('/')
		if not ipu.startswith('imagecache/'):
			return None
		idpart = ipu.split('/', 1)[1].split('?', 1)[0].strip()
		if not idpart:
			return None
		for e in ('.png', '.jpg', '.jpeg'):
			if idpart.lower().endswith(e):
				idpart = idpart[:-len(e)]
				break
		return self._sanitize_filename(idpart) or None

	def _flat_imagecache_filename(self, icon_public_url, ext='.png'):
		"""imagecache/1024 -> imagecache_1024.<ext>"""
		cid = self._imagecache_id(icon_public_url)
		return ('imagecache_%s%s' % (cid, ext)) if cid else None

	def _picon_local_path(self, icon_public_url):
		"""
		Vráti lokálnu cestu pre danú ikonku.
		Pre imagecache/* hľadá existujúci súbor v .png aj .jpg variante.
		"""
		cid = self._imagecache_id(icon_public_url)
		if cid:
			# preferuj existujúci súbor (bez ohľadu na príponu)
			for ext in ('.png', '.jpg'):
				p = os.path.join(self._img_cache_dir, 'imagecache_%s%s' % (cid, ext))
				try:
					if os.path.isfile(p) and os.path.getsize(p) > 0:
						return p
				except Exception:
					pass
			# default – PNG (bude konvertované ak PIL dostupný, inak uložené as-is)
			return os.path.join(self._img_cache_dir, 'imagecache_%s.png' % cid)
		key = self._sanitize_filename((icon_public_url or '').replace('/', '_'))
		return os.path.join(self._img_cache_dir, '%s.png' % (key or 'img'))

	def init_picons_async(self):
		"""
		Spustí sťahovanie ikoniek na pozadí (daemon thread).
		Volá sa z login() – nie z __init__ – aby neblokovala GUI pri štarte.
		"""
		t = threading.Thread(target=self._init_picons_worker)
		t.daemon = True
		t.start()

	def _log_picon(self, msg):
		try:
			import time as _t
			ts = _t.strftime('%Y-%m-%d %H:%M:%S')
			with open('/tmp/archivczsk_tvheadend_picons.log', 'a') as f:
				f.write('[%s] %s\n' % (ts, msg))
		except Exception:
			pass

	def _init_picons_worker(self):
		# Zabráň paralelným behom – len jeden worker naraz
		if not _picon_worker_lock.acquire(False):
			return
		try:
			self._init_picons_worker_inner()
		finally:
			_picon_worker_lock.release()

	def _init_picons_worker_inner(self):
		try:
			now = int(time.time())
			ttl = int(_PICON_TTL_DAYS) * 24 * 3600

			cache_has_files = False
			try:
				if os.path.isdir(self._img_cache_dir):
					cache_has_files = len(os.listdir(self._img_cache_dir)) > 0
			except Exception:
				pass

			last = 0
			if cache_has_files:
				try:
					last = int(os.path.getmtime(_PICON_STAMP))
				except Exception:
					pass

			# Stamp neplatny ak je picon adresar prazdny
			picon_dir_empty = True
			try:
				pd = '/usr/share/enigma2/picon'
				if os.path.isdir(pd):
					picon_dir_empty = len([f for f in os.listdir(pd) if f.endswith('.png')]) == 0
			except Exception:
				pass

			if last and (now - last) < ttl and cache_has_files and not picon_dir_empty:
				self._log_picon('Picon cache is fresh (last=%d, ttl=%d), skipping' % (last, ttl))
				_picon_ready_event.set()
				return

			self._log_picon('Starting picon download (cache_has_files=%s, last=%d)' % (cache_has_files, last))

			try:
				if not os.path.isdir(self._img_cache_dir):
					os.makedirs(self._img_cache_dir)
			except Exception:
				pass

			try:
				channels = self.get_channels()
			except Exception as e:
				self._log_picon('get_channels failed: %s' % e)
				return

			jobs = []
			skipped = 0
			no_icon = 0
			for ch in channels:
				icon = ch.get('icon_public_url') or ''
				if not icon:
					no_icon += 1
					continue
				if not icon.lstrip('/').startswith('imagecache/'):
					continue
				dst = self._picon_local_path(icon)
				if not dst:
					continue
				try:
					if os.path.isfile(dst) and os.path.getsize(dst) > 0:
						skipped += 1
						continue
				except Exception:
					pass
				jobs.append((icon, dst))

			self._log_picon('Channels: %d, no_icon: %d, cached: %d, to_download: %d' % (
				len(channels), no_icon, skipped, len(jobs)))

			if not jobs:
				self._write_stamp(_PICON_STAMP, now)
				self._log_picon('Nothing to download, stamp updated')
				_picon_ready_event.set()
				return

			ok_count = [0]
			err_count = [0]

			if _queue_mod is None:
				for icon, dst in jobs:
					try:
						self._download_image(icon, dst)
						ok_count[0] += 1
					except Exception as e:
						err_count[0] += 1
						self._log_picon('FAIL %s: %s' % (icon, e))
			else:
				q = _queue_mod.Queue()
				for item in jobs:
					q.put(item)

				workers = max(1, min(_PICON_MAX_WORKERS, len(jobs), 12))

				def _worker():
					sess = self.cp.get_requests_session()
					self._apply_auth_to_session(sess)
					while True:
						try:
							icon, dst = q.get_nowait()
						except Exception:
							return
						try:
							self._download_image(icon, dst, session=sess)
							ok_count[0] += 1
						except Exception as e:
							err_count[0] += 1
							self._log_picon('FAIL %s: %s' % (icon, e))
						finally:
							try:
								q.task_done()
							except Exception:
								pass

				for _ in range(workers):
					t = threading.Thread(target=_worker)
					t.daemon = True
					t.start()
				try:
					q.join()
				except Exception:
					pass

			self._write_stamp(_PICON_STAMP, now)
			self._log_picon('Done: ok=%d, err=%d' % (ok_count[0], err_count[0]))
		except Exception as e:
			self._log_picon('Worker exception: %s' % e)
		finally:
			# Vždy signalizuj – aj pri chybe – aby _post() nečakal zbytočne
			_picon_ready_event.set()

	@staticmethod
	def _write_stamp(path, now):
		try:
			with open(path, 'w') as f:
				f.write(str(now))
		except Exception:
			pass

	def make_icon_url(self, icon_public_url):
		"""
		Vráti lokálnu cestu k ikonke (z /tmp cache) alebo HTTP URL.

		NIKDY neblokuje na sieťovom stiahnutí – to by zamrzlo GUI pri renderovaní
		zoznamu kanálov. Ak súbor nie je v cache, vráti priamu HTTP URL s credentials
		(ArchivCZSK ju vie zobraziť). Sťahovanie do cache prebieha async cez init_picons_async().
		"""
		if not icon_public_url:
			return None
		if icon_public_url.startswith('file://'):
			return icon_public_url.replace('file://', '')
		if icon_public_url.startswith(('http://', 'https://', 'picon://')):
			return icon_public_url

		# Skontroluj lokálnu cache (ak async worker už stiahol)
		dst = self._picon_local_path(icon_public_url)
		try:
			if dst and os.path.isfile(dst) and os.path.getsize(dst) > 0:
				return dst
		except Exception:
			pass

		# Fallback: priama HTTP URL s credentials – žiadny blocking download
		return self._url_with_creds(self._url(icon_public_url))

	def make_icon_http_url(self, icon_public_url):
		"""Vráti absolútny HTTP URL na icon_public_url (pre EPG/bouquet export)."""
		if not icon_public_url:
			return None
		if icon_public_url.startswith('file://'):
			return None
		if icon_public_url.startswith(('http://', 'https://', 'picon://')):
			return self._url_with_creds(icon_public_url)
		return self._url_with_creds(self._url(icon_public_url))

	def _candidate_image_paths(self, icon_public_url):
		"""
		Vráti zoznam možných relatívnych ciest pre imagecache.
		TVH imagecache funguje BEZ prípony: imagecache/1644 vracia PNG.
		Prípony .png/.jpg skúšame len ako fallback.
		"""
		ipu = (icon_public_url or '').strip().lstrip('/')
		if not ipu:
			return []

		# Odstrán query string pre porovnanie
		ipu_clean = ipu.split('?', 1)[0]

		cands = []

		if ipu_clean.startswith('imagecache/'):
			idpart = ipu_clean.split('/', 1)[1].strip()
			# Zisti či má už príponu
			has_ext = any(idpart.lower().endswith(e) for e in ('.png', '.jpg', '.jpeg'))

			if has_ext:
				# Má príponu – skús s príponou aj bez
				cands.append(ipu_clean)
				base_id = idpart
				for e in ('.png', '.jpg', '.jpeg'):
					if base_id.lower().endswith(e):
						base_id = base_id[:-len(e)]
						break
				cands.append('imagecache/%s' % base_id)
			else:
				# Bez prípony – skús priamo (TVH to zvládne), potom s príponami
				cands.append(ipu_clean)          # imagecache/1644  ← funguje na TVH
				cands.append('%s.png' % ipu_clean)  # imagecache/1644.png
				# .jpg netreba – TVH vždy vracia PNG z imagecache
		else:
			cands.append(ipu_clean)

		# Ak mal query string, pridaj aj bez neho
		if '?' in ipu and ipu_clean not in cands:
			cands.append(ipu_clean)

		# Deduplikácia
		seen = set()
		out = []
		for p in cands:
			if p and p not in seen:
				seen.add(p)
				out.append(p)
		return out

	@staticmethod
	def _ctype_to_ext(ctype):
		"""Content-Type -> prípona súboru."""
		ctype = (ctype or '').lower().split(';')[0].strip()
		if 'jpeg' in ctype or 'jpg' in ctype:
			return '.jpg'
		if 'png' in ctype:
			return '.png'
		if 'gif' in ctype:
			return '.gif'
		if 'svg' in ctype:
			return '.svg'
		if 'webp' in ctype:
			return '.webp'
		return '.png'  # default

	@staticmethod
	def _sniff_ext(data):
		"""Zistí formát z magic bytes (prvých 16 bajtov)."""
		if data[:8] == b'\x89PNG\r\n\x1a\n':
			return '.png'
		if data[:3] == b'\xff\xd8\xff':
			return '.jpg'
		if data[:6] in (b'GIF87a', b'GIF89a'):
			return '.gif'
		if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
			return '.webp'
		if data[:5] in (b'<?xml', b'<svg ') or b'<svg' in data[:64]:
			return '.svg'
		return None  # neznámy

	def _download_image(self, icon_public_url, dst_path, session=None):
		"""
		Stiahne obrázok a uloží do dst_path.

		Kľúčová logika:
		1. Zistí skutočný formát z Content-Type + magic bytes
		2. Ak je PIL dostupný → konvertuje na RGBA PNG (transparentnosť!)
		3. Ak PIL nie je → uloží so správnou príponou (NIKDY JPEG ako .png)
		4. dst_path sa môže zmeniť (ak skutočná prípona != požadovaná)
		   → vracia skutočnú cestu uloženého súboru
		"""
		if not icon_public_url or not dst_path:
			raise AddonErrorException("Missing icon_public_url/dst_path")

		sess = session if session is not None else self.req
		if session is None:
			self._apply_auth_to_session()

		dst_dir = os.path.dirname(dst_path)
		if dst_dir:
			try:
				if not os.path.isdir(dst_dir):
					os.makedirs(dst_dir)
			except Exception:
				pass

		last_err = None
		for rel in self._candidate_image_paths(icon_public_url):
			url = self._url(rel)
			# Retry pri dočasných chybách (5xx, timeout) – max 3 pokusy
			r = None
			for attempt in range(3):
				try:
					r = sess.get(url, timeout=self._timeout(), stream=True)
					break  # úspech
				except Exception as e:
					last_err = e
					if attempt < 2:
						time.sleep(0.5 * (attempt + 1))
						continue
			if r is None:
				continue
			if r.status_code == 404:
				# 404 = obrázok neexistuje, nema zmysel opakovať
				last_err = Exception("HTTP 404 for %s" % url)
				continue
			if r.status_code >= 500:
				# 5xx = dočasná chyba servera, skús znova
				for attempt in range(2):
					time.sleep(1.0 * (attempt + 1))
					try:
						r = sess.get(url, timeout=self._timeout(), stream=True)
						if r.status_code == 200:
							break
					except Exception as e:
						last_err = e
			if r.status_code != 200:
				last_err = Exception("HTTP %s for %s" % (r.status_code, url))
				continue
			ctype = (r.headers.get('Content-Type') or '').lower()
			if ctype and not ctype.startswith('image/'):
				last_err = Exception("Not an image: %s" % ctype)
				continue

			# Načítaj celý obsah do pamäte (ikonky sú malé, typicky <50KB)
			try:
				raw = r.content
			except Exception as e:
				last_err = e
				continue

			if not raw:
				last_err = Exception("Empty response for %s" % url)
				continue

			# Zisti skutočný formát
			real_ext = self._sniff_ext(raw[:16])
			if real_ext is None:
				real_ext = self._ctype_to_ext(ctype)

			# --- PIL dostupný: konvertuj na RGBA PNG → transparentnosť v Enigma2 ---
			if _PIL_OK:
				try:
					import io as _io_mod
					img = _PIL_Image.open(_io_mod.BytesIO(raw))
					# Zachovaj transparentnosť: RGBA alebo P (palette s transparentnosťou)
					if img.mode == 'P' and 'transparency' in img.info:
						img = img.convert('RGBA')
					elif img.mode not in ('RGBA', 'LA'):
						img = img.convert('RGBA')
					# Vždy ukladaj ako PNG (transparentnosť!)
					final_path = dst_path if dst_path.lower().endswith('.png') else (
						os.path.splitext(dst_path)[0] + '.png'
					)
					tmp = final_path + '.tmp'
					img.save(tmp, format='PNG', optimize=False)
					try:
						if os.path.exists(final_path):
							os.remove(final_path)
					except Exception:
						pass
					os.rename(tmp, final_path)
					return final_path
				except Exception as e:
					last_err = e
					# PIL zlyhalo → fallback na raw uloženie

			# --- Bez PIL: uloži raw bytes so SPRÁVNOU príponou ---
			# NIKDY neukladaj JPEG obsah do .png súboru!
			final_path = dst_path
			dst_base = os.path.splitext(dst_path)[0]
			if real_ext and not dst_path.lower().endswith(real_ext):
				final_path = dst_base + real_ext
				# Ak existuje starý .png so zlým obsahom, zmaž ho
				if final_path != dst_path:
					try:
						if os.path.exists(dst_path):
							os.remove(dst_path)
					except Exception:
						pass

			tmp = final_path + '.tmp'
			try:
				with open(tmp, 'wb') as f:
					f.write(raw)
				try:
					if os.path.exists(final_path):
						os.remove(final_path)
				except Exception:
					pass
				os.rename(tmp, final_path)
				return final_path
			except Exception as e:
				last_err = e
				try:
					os.remove(tmp)
				except Exception:
					pass
				continue

		raise AddonErrorException("Image download failed: %s" % (str(last_err) if last_err else "unknown"))

	# ------------------------------------------------------------------
	# Channel / tag / DVR / EPG API
	# ------------------------------------------------------------------

	def get_tags(self):
		return self.api_get_all('api/channeltag/grid', {'start': 0}, page_limit=200)

	def get_channels(self, force=False):
		"""Vráti zoznam kanálov. Výsledok sa cachuje na 60 sekúnd."""
		if not force and Tvheadend._channels_cache is not None:
			cached = Tvheadend._channels_cache.get('channels')
			if cached is not None:
				return cached
		result = self.api_get_all('api/channel/grid', {'start': 0}, page_limit=1000)
		if Tvheadend._channels_cache is not None:
			Tvheadend._channels_cache.put('channels', result)
		return result

	def invalidate_channels_cache(self):
		"""Zmaže cache kanálov."""
		if Tvheadend._channels_cache is not None:
			Tvheadend._channels_cache.invalidate('channels')

	def get_channels_by_tag(self, tag_uuid):
		channels = self.get_channels()
		if not tag_uuid:
			return channels
		return [ch for ch in channels if tag_uuid in (ch.get('tags') or [])]

	def get_dvr_finished(self):
		return self.api_get_all('api/dvr/entry/grid_finished', {'start': 0}, page_limit=500)

	def get_epg_now(self, limit=5000):
		"""Vráti dict {channelUuid: event} pre práve bežiace programy."""
		try:
			data = self.api_get("api/epg/events/grid", params={"mode": "now", "limit": int(limit)})
		except Exception:
			return {}
		out = {}
		for e in (data.get("entries") or []):
			ch = e.get("channelUuid")
			if ch:
				out[ch] = e
		return out

	def get_epg_now_next(self, channel_uuid):
		"""Vráti (now_event, next_event) pre daný kanál."""
		if not channel_uuid:
			return (None, None)

		def _fetch(mode):
			params = {'mode': mode, 'limit': 1, 'start': 0, 'channel': channel_uuid}
			try:
				data = self.api_get('api/epg/events/grid', params=params) or {}
			except Exception:
				return None
			entries = data.get('entries')
			if entries:
				return entries[0]
			# fallback – niektoré verzie TVH používajú channelUuid
			params.pop('channel', None)
			params['channelUuid'] = channel_uuid
			try:
				data = self.api_get('api/epg/events/grid', params=params) or {}
			except Exception:
				return None
			entries = data.get('entries')
			return entries[0] if entries else None

		now_event = next_event = None
		try:
			now_event = _fetch('now')
		except Exception:
			pass
		try:
			next_event = _fetch('next')
		except Exception:
			pass
		return (now_event, next_event)

	def get_channel_name_by_service_uuid(self, service_uuid):
		if not service_uuid:
			return None
		try:
			for ch in self.get_channels():
				if service_uuid in (ch.get('services') or []):
					return ch.get('name') or None
		except Exception:
			pass
		return None
