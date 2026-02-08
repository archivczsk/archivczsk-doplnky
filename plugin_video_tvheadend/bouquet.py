# -*- coding: utf-8 -*-

import hashlib
import os
import shutil
import base64
import re
import time
import unicodedata

# -------------------------------------------------
# Python 2/3 compatibility
# -------------------------------------------------
try:
	import threading
except Exception:
	threading = None

try:
	basestring
except NameError:
	basestring = (str, bytes)

# urllib parsing (py3: urllib.parse, py2: urlparse)
try:
	import urllib.parse as urllib_parse
except Exception:
	try:
		import urlparse as urllib_parse
	except Exception:
		urllib_parse = None

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator

# ✅ We will override default bouquet generator (without editing bouquet_xmlepg.py)
try:
	from tools_archivczsk.generator.bouquet import BouquetGeneratorTemplate
except Exception:
	# fallback (just in case of different import path)
	from tools_archivczsk.generator.bouquet_xmlepg import BouquetGeneratorTemplate


_PICON_LOG = "/tmp/archivczsk_tvheadend_picons.log"


class CustomBouquetGenerator(BouquetGeneratorTemplate):
	"""
	Custom BouquetGenerator which supports per-type custom bouquet display name
	via settings:
	  - userbouquet_custom_name_tv
	  - userbouquet_custom_name_radio
	No need to edit bouquet_xmlepg.py
	"""

	def __init__(self, bxeg, channel_type=None):
		# prefix used for filenames / bouquet identifiers
		if channel_type:
			self.prefix = bxeg.prefix + '_' + channel_type
		else:
			self.prefix = bxeg.prefix

		# --- build display name ---
		self.name = self._get_display_name(bxeg, channel_type)

		# keep original profile suffix behavior
		profile_info = bxeg.get_profile_info()
		if profile_info is not None:
			self.prefix = self.prefix + '_' + profile_info[0]
			self.name = self.name + ' - ' + profile_info[1]

		self.bxeg = bxeg
		self.sid_start = bxeg.sid_start
		self.tid = bxeg.tid
		self.onid = bxeg.onid
		self.namespace = bxeg.namespace
		self.channel_type = channel_type

		BouquetGeneratorTemplate.__init__(
			self,
			bxeg.http_endpoint,
            False,  # enable_adult (setting nepouzivas)
			bxeg.get_setting('enable_xmlepg'),
			bxeg.get_setting('enable_picons'),
			bxeg.get_setting('player_name'),
			bxeg.user_agent
		)

	def _get_display_name(self, bxeg, channel_type):
		"""
		Return custom bouquet name if configured, otherwise fallback to original naming.
		Important: This avoids hardcoded "bxeg.name + ' ' + channel_type" in default generator.
		"""
		try:
			ctype = channel_type or 'tv'
			if ctype == 'radio':
				custom = bxeg.get_setting('userbouquet_custom_name_radio')
			else:
				custom = bxeg.get_setting('userbouquet_custom_name_tv')

			custom = (custom or '').strip()
			if custom:
				return custom
		except Exception:
			pass

		# fallback (original logic)
		if channel_type:
			return bxeg.name + ' ' + channel_type
		return bxeg.name

	def get_channels(self):
		return self.bxeg.get_bouquet_channels(self.channel_type)


class TvheadendBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):
	"""
	Tvheadend -> ArchivCZSK bouquet + xmlepg + enigmaepg generator
	"""

	def __init__(self, content_provider):
		self.cp = content_provider

		# POZOR: enable_userbouquet_cam u teba neexistuje -> spôsobovalo AttributeError
		self.bouquet_settings_names = (
			'enable_userbouquet',
			'enable_userbouquet_radio',
			# 'enable_userbouquet_cam',   # ❌ removed due to AttributeError
			'userbouquet_categories',

			# ✅ NEW settings (custom bouquet display names)
			'userbouquet_custom_name_tv',
			'userbouquet_custom_name_radio',

			'enable_xmlepg',
			'xmlepg_dir',
			'xmlepg_days',
			'enable_picons',
			'player_name',
			'enigmaepg_days',
		)

		# ✅ support TV + RADIO
		BouquetXmlEpgGenerator.__init__(self, content_provider, channel_types=('tv', 'radio'))

		# ✅ override bouquet generator without touching bouquet_xmlepg.py
		self.bouquet_generator = CustomBouquetGenerator

		self._channels = []
		self._key_to_url = {}
		self._epg_cache = None
		self._tagmap = None

		# ✅ TAG ORDER CACHE (sorting categories according to TVH "index")
		self._taguuid_to_order = None        # uuid -> index
		self._tagnorm_to_order = None        # normalized-name -> index

	# -------------------------------------------------
	# logging helper
	# -------------------------------------------------

	def _log(self, msg):
		try:
			ts = time.strftime("%Y-%m-%d %H:%M:%S")
			with open(_PICON_LOG, "a") as f:
				f.write("[%s] %s\n" % (ts, msg))
		except Exception:
			pass

	# -------------------------------------------------
	# ✅ settings read (fallback /etc/enigma2/settings)
	# -------------------------------------------------

	def _read_e2_setting_raw(self, key):
		try:
			fn = "/etc/enigma2/settings"
			if not os.path.isfile(fn):
				return None
			prefix = key + "="
			with open(fn, "r") as f:
				for line in f:
					line = line.strip()
					if not line or line.startswith("#"):
						continue
					if line.startswith(prefix):
						return line.split("=", 1)[1].strip()
		except Exception:
			return None
		return None

	def _to_bool(self, v, default=False):
		if isinstance(v, bool):
			return v
		if v is None:
			return default
		try:
			s = str(v).strip().lower()
		except Exception:
			return default
		if s in ("1", "true", "yes", "on", "enabled"):
			return True
		if s in ("0", "false", "no", "off", "disabled"):
			return False
		return default

	def _to_int(self, v, default=0):
		try:
			return int(v)
		except Exception:
			return default

	def get_setting(self, name):
		try:
			val = self.cp.get_setting(name)
		except Exception:
			val = None

		e2_key = "config.plugins.archivCZSK.archives.tvheadend.%s" % name
		raw = self._read_e2_setting_raw(e2_key)

		if name in (
			"enable_userbouquet", "enable_userbouquet_radio",
			"userbouquet_categories", "enable_xmlepg",
			"enable_picons"
		):
			if val is not None:
				return self._to_bool(val, default=False)
			return self._to_bool(raw, default=False)

		if name in ("xmlepg_days", "enigmaepg_days"):
			if val is not None:
				return self._to_int(val, default=0)
			return self._to_int(raw, default=0)

		# text settings
		if name in ("xmlepg_dir", "player_name", "userbouquet_custom_name_tv", "userbouquet_custom_name_radio"):
			if val is not None and val != "":
				return val
			return raw if raw is not None else ""

		return val if val is not None else raw

	# -------------------------------------------------

	def logged_in(self):
		return True

	def translate(self, txt):
		try:
			return self.cp._(txt)
		except Exception:
			return txt

	# -------------------------------------------------
	# ✅ TVH TAGS -> RADIO DETECT (+ categories)
	# -------------------------------------------------

	def _strip_accents(self, s):
		try:
			s = unicodedata.normalize("NFKD", s)
			return "".join([c for c in s if not unicodedata.combining(c)])
		except Exception:
			return s

	def _normalize_tag_name(self, s):
		s = (s or "").strip().lower()
		s = self._strip_accents(s)   # rádio -> radio
		s = re.sub(r"\s+", " ", s)
		return s

	def _safe_int(self, v, default=10**6):
		try:
			return int(v)
		except Exception:
			return default

	def _get_tag_uuid_to_name(self):
		# ✅ if cache ready, return
		if self._tagmap is not None and self._taguuid_to_order is not None and self._tagnorm_to_order is not None:
			return self._tagmap

		self._tagmap = {}
		self._taguuid_to_order = {}
		self._tagnorm_to_order = {}

		try:
			tags = self.cp.tvh.get_tags() or []
		except Exception:
			tags = []

		# TVH returns "index" (important for ordering)
		for t in tags:
			u = (t.get('uuid') or '').strip()
			n = (t.get('name') or t.get('val') or '').strip()
			if not u or not n:
				continue

			self._tagmap[u] = n

			idx = self._safe_int(t.get('index', None), default=10**6)
			if idx == 10**6:
				idx = self._safe_int(t.get('order', None), default=10**6)

			if (u not in self._taguuid_to_order) or (idx < self._taguuid_to_order.get(u, 10**6)):
				self._taguuid_to_order[u] = idx

			nn = self._normalize_tag_name(n)
			if nn:
				if (nn not in self._tagnorm_to_order) or (idx < self._tagnorm_to_order.get(nn, 10**6)):
					self._tagnorm_to_order[nn] = idx

		return self._tagmap

	def _is_radio_by_tags(self, tag_uuids):
		radio_tokens = (
			"radio", "radia", "radia fm", "radio fm",
			"radiostanice", "radiostanica",
			"rádio", "rádia", "rádiá",
		)

		tagmap = self._get_tag_uuid_to_name()
		for tu in (tag_uuids or []):
			n = self._normalize_tag_name(tagmap.get(tu) or "")
			if not n:
				continue

			for tok in radio_tokens:
				tokn = self._normalize_tag_name(tok)
				if n == tokn or tokn in n:
					return True

		return False

	def _get_channel_categories(self, ch):
		out = []
		tagmap = self._get_tag_uuid_to_name()
		for tu in (ch.get("tags") or []):
			n = (tagmap.get(tu) or "").strip()
			if n:
				out.append(n)
		return out

	def _category_order(self, cat_name):
		"""
		Category order:
		- based on TVH "index" (api/channeltag/grid)
		- "Ostatné" always last
		- fallback: big number
		"""
		if not cat_name:
			return 10**6

		nn = self._normalize_tag_name(cat_name)
		if nn in ("ostatne", "ostatné"):
			return 10**9

		self._get_tag_uuid_to_name()
		if self._tagnorm_to_order and nn in self._tagnorm_to_order:
			return self._safe_int(self._tagnorm_to_order.get(nn), default=10**6)

		return 10**6

	# -------------------------------------------------
	# CHANNELS
	# -------------------------------------------------

	def get_channels_checksum(self, channel_type):
		if channel_type not in ('tv', 'radio'):
			return '0'

		if not self._channels:
			self.load_channel_list()

		want_radio = (channel_type == 'radio')

		h = hashlib.md5()
		for ch in self._channels:
			if bool(ch.get('is_radio')) != want_radio:
				continue
			s = "%s|%s|%s|%s|%s" % (
				ch.get('uuid', ''),
				ch.get('name', ''),
				ch.get('id', 0),
				ch.get('icon_public_url') or '',
				'R' if ch.get('is_radio') else 'T'
			)
			h.update(s.encode('utf-8', errors='ignore'))
		return h.hexdigest()

	def load_channel_list(self):
		self._channels = []
		self._key_to_url = {}
		self._epg_cache = None
		self._tagmap = None

		# reset tag-order cache
		self._taguuid_to_order = None
		self._tagnorm_to_order = None

		try:
			channels = self.cp.tvh.get_channels() or []
		except Exception:
			channels = []

		channels = [c for c in channels if c.get('enabled', True)]

		def _num(x):
			try:
				return int(x.get('number') or 0)
			except Exception:
				return 0

		channels = sorted(channels, key=_num)

		fallback_id = 10000
		for ch in channels:
			uuid = ch.get('uuid') or ''
			if not uuid:
				continue

			name = ch.get('name') or uuid
			number = _num(ch)

			service_uuid = ''
			try:
				services = ch.get('services') or []
				if services:
					service_uuid = services[0]
			except Exception:
				service_uuid = ''

			try:
				url = self.cp.tvh.make_live_stream_url(
					channel_uuid=uuid,
					service_uuid=(service_uuid or None)
				)
			except Exception:
				continue

			icon_public_url = (ch.get('icon_public_url') or '').strip()

			try:
				is_radio = self._is_radio_by_tags(ch.get('tags') or [])
			except Exception:
				is_radio = False

			ch_id = number if number > 0 else fallback_id
			if number <= 0:
				fallback_id += 1

			item = {
				'uuid': uuid,
				'name': name,
				'id': int(ch_id),
				'key': uuid,
				'adult': False,
				'picon': None,
				'icon_public_url': icon_public_url,
				'is_radio': bool(is_radio),
				'tags': ch.get('tags') or [],
			}

			self._channels.append(item)
			self._key_to_url[uuid] = url

		return True

	def get_url_by_channel_key(self, channel_key):
		return self._key_to_url.get(channel_key, '')

	def get_bouquet_channels(self, channel_type=None):
		if not self._channels:
			self.load_channel_list()

		want_radio = (channel_type == 'radio')
		use_categories = self.get_setting("userbouquet_categories")

		# FIX: if separate radio bouquet is enabled, TV bouquet must not contain radio channels
		separate_radio = self.get_setting("enable_userbouquet_radio")

		if not use_categories:
			for ch in self._channels:
				if (channel_type == 'tv') and separate_radio and bool(ch.get('is_radio')):
					continue

				if bool(ch.get('is_radio')) != want_radio:
					continue
				yield {
					'name': ch['name'],
					'id': ch['id'],
					'key': ch['key'],
					'adult': False,
					'picon': None,
					'is_separator': False,
				}
			return

		categories = {}
		for ch in self._channels:
			if (channel_type == 'tv') and separate_radio and bool(ch.get('is_radio')):
				continue

			if bool(ch.get('is_radio')) != want_radio:
				continue

			cats = self._get_channel_categories(ch)
			if not cats:
				cats = ["Ostatné"]

			for c in cats:
				categories.setdefault(c, []).append(ch)

		for cat in sorted(
			categories.keys(),
			key=lambda x: (
				self._category_order(x),
				self._strip_accents(x).lower()
			)
		):
			yield {
				'name': "--- %s ---" % cat,
				'is_separator': True,
			}
			for ch in categories[cat]:
				yield {
					'name': ch['name'],
					'id': ch['id'],
					'key': ch['key'],
					'adult': False,
					'picon': None,
					'is_separator': False,
				}

	def get_xmlepg_channels(self):
		if not self._channels:
			self.load_channel_list()

		for ch in self._channels:
			id_content = (ch['uuid'] or '').replace('-', '_')
			yield {
				'name': ch['name'],
				'id': ch['id'],
				'id_content': id_content,
				'key': ch['uuid'],
			}

	# -------------------------------------------------
	# ✅ PICONY
	# -------------------------------------------------

	def _serviceref_to_picon_name(self, service_ref):
		sr = (service_ref or "").strip()
		if not sr:
			return None
		if sr.endswith(":"):
			sr = sr[:-1]
		parts = sr.split(":")
		core = parts[:10] if len(parts) >= 10 else parts
		core = [p.strip() for p in core if p is not None]

		name = "_".join(core)
		name = re.sub(r"[^0-9A-Za-z_]+", "_", name)
		while "__" in name:
			name = name.replace("__", "_")

		return name + ".png"

	def _find_bouquet_files(self):
		out = []
		base = "/etc/enigma2"
		try:
			for fn in os.listdir(base):
				if fn.startswith("userbouquet.") and (fn.endswith(".tv") or fn.endswith(".radio")):
					out.append(os.path.join(base, fn))
		except Exception:
			pass
		return out

	def _is_tvheadend_bouquet_file(self, filepath):
		try:
			with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
				for _ in range(0, 200):
					line = f.readline()
					if not line:
						break
					if "/tvheadend/" in line:
						return True
		except Exception:
			return False
		return False

	def _build_uuid_to_iconpublic(self):
		m = {}
		for ch in self._channels:
			u = (ch.get("uuid") or "").strip()
			ipu = (ch.get("icon_public_url") or "").strip()
			if u and ipu:
				m[u] = ipu
		return m

	def _normalize_name(self, s):
		s = (s or "").strip().lower()
		s = re.sub(r"\s+", " ", s)
		return s

	def _build_name_to_iconpublic(self):
		m = {}
		for ch in self._channels:
			n = self._normalize_name(ch.get("name") or "")
			ipu = (ch.get("icon_public_url") or "").strip()
			if n and ipu:
				m[n] = ipu
		return m

	def _tmp_cache_path_from_iconpublic(self, icon_public_url):
		ipu = (icon_public_url or "").strip()
		if not ipu:
			return None
		ipu = ipu.split("?", 1)[0].lstrip("/")
		if not ipu.startswith("imagecache/"):
			return None
		idpart = ipu.split("/", 1)[1].strip()
		if not idpart:
			return None

		idlower = idpart.lower()
		for ext in (".png", ".jpg", ".jpeg"):
			if idlower.endswith(ext):
				idpart = idpart[:-len(ext)]
				break

		idpart = re.sub(r"[^a-zA-Z0-9_.-]+", "_", idpart)
		if not idpart:
			return None

		return "/tmp/archivczsk_tvheadend_img/imagecache_%s.png" % idpart

	def _same_size_kb(self, a, b):
		try:
			if not os.path.isfile(a) or not os.path.isfile(b):
				return False
			aa = os.path.getsize(a)
			bb = os.path.getsize(b)
			if aa <= 0 or bb <= 0:
				return False
			ka = int((aa + 1023) / 1024)
			kb = int((bb + 1023) / 1024)
			return ka == kb
		except Exception:
			return False

	def _copy_if_newer(self, src, dst):
		try:
			if not os.path.isfile(src) or os.path.getsize(src) <= 0:
				return False
		except Exception:
			return False

		if self._same_size_kb(src, dst):
			return False

		try:
			src_m = int(os.path.getmtime(src))
		except Exception:
			src_m = 0

		try:
			dst_m = int(os.path.getmtime(dst)) if os.path.isfile(dst) else 0
		except Exception:
			dst_m = 0

		if (not os.path.isfile(dst)) or (src_m > dst_m):
			try:
				shutil.copyfile(src, dst)
				try:
					os.chmod(dst, 0o644)
				except Exception:
					pass
				return True
			except Exception:
				return False

		return False

	def _looks_like_uuid(self, s):
		s = (s or "").strip()
		if not s:
			return False
		if re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", s):
			return True
		if re.match(r"^[0-9a-fA-F]{32}$", s):
			return True
		return False

	def _b64_to_text(self, token):
		try:
			t = (token or "").strip()
			if not t:
				return None
			pad = "=" * (-len(t) % 4)
			raw = base64.b64decode((t + pad).encode("utf-8"))
			return raw.decode("utf-8", errors="ignore").strip()
		except Exception:
			return None

	def _extract_url_from_service_ref(self, service_ref):
		sr = (service_ref or "").strip()
		if not sr:
			return None
		last = sr.split(":")[-1].strip()
		if not last:
			return None
		try:
			if urllib_parse is None:
				return last
			try:
				return urllib_parse.unquote(last)
			except Exception:
				return last
		except Exception:
			return last

	def _extract_channel_uuid(self, service_ref):
		u = self._extract_url_from_service_ref(service_ref)
		if not u:
			return None

		m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", u)
		if m:
			return m.group(1)

		m = re.search(r"/tvheadend/(?:playlive|playliveTV|play|stream|live)/([^/?#]+)", u)
		if m:
			token = m.group(1).strip()
			if self._looks_like_uuid(token):
				return token
			dec = self._b64_to_text(token)
			if dec and self._looks_like_uuid(dec):
				return dec

		try:
			pu = urllib_parse.urlparse(u) if urllib_parse else None
			qs = {}
			try:
				if pu is not None and urllib_parse:
					qs = urllib_parse.parse_qs(pu.query or "")
			except Exception:
				qs = {}
			for k in ("uuid", "channel", "channel_uuid", "id", "key", "ch", "k"):
				if k in qs and qs[k]:
					token = (qs[k][0] or "").strip()
					if self._looks_like_uuid(token):
						return token
					dec = self._b64_to_text(token)
					if dec and self._looks_like_uuid(dec):
						return dec
		except Exception:
			pass

		try:
			try:
				path = (urllib_parse.urlparse(u).path or "") if urllib_parse else ""
			except Exception:
				path = ""
			last = path.rstrip("/").split("/")[-1].strip()
			if last:
				if self._looks_like_uuid(last):
					return last
				dec = self._b64_to_text(last)
				if dec and self._looks_like_uuid(dec):
					return dec
		except Exception:
			pass

		return None

	def _pick_picon_dir(self, preferred="/usr/share/enigma2/picon"):
		cands = [
			preferred,
			"/usr/share/enigma2/picon",
			"/media/hdd/picon",
			"/media/usb/picon",
			"/etc/enigma2/picon",
		]
		for d in cands:
			try:
				if not os.path.isdir(d):
					os.makedirs(d)
			except Exception:
				pass
			try:
				testf = os.path.join(d, ".write_test")
				with open(testf, "w") as f:
					f.write("1")
				os.remove(testf)
				return d
			except Exception:
				continue
		return None

	def download_picons_from_bouquets(self, preferred_dir="/usr/share/enigma2/picon"):
		if not self.get_setting("enable_picons"):
			self._log("enable_picons=false -> skip")
			return
		if not self.get_setting("enable_userbouquet") and not self.get_setting("enable_userbouquet_radio"):
			self._log("enable_userbouquet=false and enable_userbouquet_radio=false -> skip")
			return

		if not self._channels:
			self.load_channel_list()

		uuid2icon = self._build_uuid_to_iconpublic()
		name2icon = self._build_name_to_iconpublic()

		picon_dir = self._pick_picon_dir(preferred=preferred_dir)
		if not picon_dir:
			self._log("No writable picon dir")
			return

		files = self._find_bouquet_files()
		if not files:
			self._log("No bouquet files in /etc/enigma2")
			return

		tvfiles = [f for f in files if self._is_tvheadend_bouquet_file(f)]
		if not tvfiles:
			self._log("No Tvheadend bouquet detected by content (/tvheadend/* not found)")
			return

		total_service = 0
		total_uuid = 0
		total_name = 0
		total_skipped_same = 0
		total_copied = 0
		total_downloaded = 0

		for bq in tvfiles:
			try:
				with open(bq, "r", encoding="utf-8", errors="ignore") as f:
					lines = [x.rstrip("\n") for x in f]
			except Exception:
				continue

			last_service_ref = None

			for line in lines:
				if line.startswith("#SERVICE "):
					rest = line[len("#SERVICE "):].strip()
					service_ref = rest.split(" ", 1)[0].strip()
					last_service_ref = service_ref
					total_service += 1
					continue

				if line.startswith("#DESCRIPTION ") and last_service_ref:
					name = line[len("#DESCRIPTION "):].strip()

					icon_public = None
					channel_uuid = self._extract_channel_uuid(last_service_ref)
					if channel_uuid:
						total_uuid += 1
						icon_public = uuid2icon.get(channel_uuid)

					if not icon_public:
						icon_public = name2icon.get(self._normalize_name(name))
						if icon_public:
							total_name += 1

					if not icon_public:
						last_service_ref = None
						continue

					picon_name = self._serviceref_to_picon_name(last_service_ref)
					if not picon_name:
						last_service_ref = None
						continue

					dst = os.path.join(picon_dir, picon_name)

					src = self._tmp_cache_path_from_iconpublic(icon_public)
					if src and self._same_size_kb(src, dst):
						total_skipped_same += 1
						last_service_ref = None
						continue

					if src and self._copy_if_newer(src, dst):
						total_copied += 1
						last_service_ref = None
						continue

					try:
						self.cp.tvh.download_image_to_file(icon_public, dst)
						try:
							os.chmod(dst, 0o644)
						except Exception:
							pass
						total_downloaded += 1
					except Exception:
						pass

					last_service_ref = None

		self._log("Picons: services=%d uuidHits=%d nameHits=%d skippedSameKB=%d copied=%d downloaded=%d" %
				  (total_service, total_uuid, total_name, total_skipped_same, total_copied, total_downloaded))

	def download_picons(self, *args, **kwargs):
		self.download_picons_from_bouquets(preferred_dir="/usr/share/enigma2/picon")

	# -------------------------------------------------
	# ✅ RADIO bouquet fix (unchanged)
	# -------------------------------------------------

	def _read_lines(self, path):
		try:
			if not os.path.isfile(path):
				return []
			with open(path, "r", encoding="utf-8", errors="ignore") as f:
				return f.read().splitlines()
		except Exception:
			return []

	def _write_lines(self, path, lines):
		try:
			with open(path, "w") as f:
				f.write("\n".join(lines) + "\n")
			return True
		except Exception:
			return False

	def _ensure_bouquets_radio_has(self, bouquet_filename):
		base = "/etc/enigma2"
		br = os.path.join(base, "bouquets.radio")

		line_need = '#SERVICE 1:7:2:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % bouquet_filename

		lines = self._read_lines(br)
		if not lines:
			lines = [
				'#NAME Bouquets (Radio)',
				line_need,
			]
			if self._write_lines(br, lines):
				self._log("Created bouquets.radio + added %s" % bouquet_filename)
			return

		for ln in lines:
			if bouquet_filename in ln and "FROM BOUQUET" in ln:
				return

		out = []
		inserted = False
		for ln in lines:
			out.append(ln)
			if (not inserted) and ln.startswith("#NAME"):
				out.append(line_need)
				inserted = True
		if not inserted:
			out.append(line_need)

		if self._write_lines(br, out):
			self._log("Patched bouquets.radio: added %s" % bouquet_filename)

	def _remove_from_bouquets_tv(self, bouquet_filenames):
		base = "/etc/enigma2"
		bt = os.path.join(base, "bouquets.tv")

		lines = self._read_lines(bt)
		if not lines:
			return

		def _hit(line):
			for b in bouquet_filenames:
				if ('FROM BOUQUET "%s"' % b) in line:
					return True
			return False

		new_lines = [ln for ln in lines if not _hit(ln)]
		if new_lines != lines:
			if self._write_lines(bt, new_lines):
				self._log("Removed radio bouquet(s) from bouquets.tv: %s" % (", ".join(bouquet_filenames)))

	def _fix_radio_bouquet_filenames(self):
		if not self.get_setting("enable_userbouquet_radio"):
			return

		base = "/etc/enigma2"
		try:
			files = os.listdir(base)
		except Exception:
			return

		remove_from_tv = []

		renamed_to = []
		for fn in files:
			lfn = fn.lower()
			if not fn.startswith("userbouquet."):
				continue
			if not fn.endswith(".tv"):
				continue
			if not (("radio" in lfn) or ("radia" in lfn) or ("rádio" in lfn) or ("rádia" in lfn)):
				continue

			src = os.path.join(base, fn)

			dst_fn = fn[:-3] + ".radio"
			dst = os.path.join(base, dst_fn)

			remove_from_tv.append(fn)

			try:
				if os.path.isfile(dst):
					try:
						os.remove(src)
					except Exception:
						pass
					renamed_to.append(dst_fn)
					continue

				os.rename(src, dst)
				renamed_to.append(dst_fn)
				self._log("Radio bouquet rename: %s -> %s" % (fn, dst_fn))
			except Exception:
				continue

		br = os.path.join(base, "bouquets.radio")
		lines = self._read_lines(br)
		if lines:
			new_lines = []
			changed = False
			for line in lines:
				m = re.search(r'FROM BOUQUET \"(userbouquet\.[^\"]+)\.tv\"', line)
				if m:
					base_name = m.group(1)
					new_line = line.replace(base_name + ".tv", base_name + ".radio")
					if new_line != line:
						changed = True
						line = new_line
				new_lines.append(line)
			if changed and self._write_lines(br, new_lines):
				self._log("Patched bouquets.radio references (.tv -> .radio)")

		for fn in list(remove_from_tv):
			remove_from_tv.append(fn[:-3] + ".radio")
		self._remove_from_bouquets_tv(sorted(set(remove_from_tv)))

		target = "userbouquet.tvheadend_radio.radio"
		if os.path.isfile(os.path.join(base, target)):
			self._ensure_bouquets_radio_has(target)
			return

		try:
			for fn in os.listdir(base):
				lfn = fn.lower()
				if not fn.startswith("userbouquet.") or not fn.endswith(".radio"):
					continue
				if "tvheadend" in lfn and ("radio" in lfn or "radia" in lfn or "rádio" in lfn or "rádia" in lfn):
					self._ensure_bouquets_radio_has(fn)
					return
		except Exception:
			pass

		if renamed_to:
			self._ensure_bouquets_radio_has(renamed_to[0])

	def refresh_userbouquet_start(self, *args, **kwargs):
		"""Spustí refresh userbouquet-u v background taske.

		Dôležité: Toto sa môže volať aj z GUI threadu (napr. v login()), preto tu
		nesmieme robiť dlhé sleep/IO operácie. Dodatočné opravy (radio filenames + picons)
		odpálime oneskorene cez Timer.
		"""
		try:
			ret = BouquetXmlEpgGenerator.refresh_userbouquet_start(self, *args, **kwargs)
		except Exception:
			ret = None

		def _post():
			try:
				self._fix_radio_bouquet_filenames()
			except Exception:
				pass
			try:
				self.download_picons()
			except Exception:
				pass

		try:
			if threading is not None:
				t = threading.Timer(1.0, _post)
				t.daemon = True
				t.start()
			else:
				# fallback: spusti hneď, ale aspoň bez sleep slučky
				_post()
		except Exception:
			pass

		return ret

	# -------------------------------------------------
	# FAST EPG
	# -------------------------------------------------

	def _pick(self, val):
		if not val:
			return ""
		if isinstance(val, basestring):
			return val
		if isinstance(val, dict):
			for k in ('slk', 'slo', 'ces', 'cze', 'eng'):
				if k in val and val[k]:
					return val[k]
			for v in val.values():
				if v:
					return v
		return ""

	def get_epg(self, channel, fromts, tots):
		ch_uuid = channel.get('key') or ''
		if not ch_uuid:
			return

		fromts_i = int(fromts)
		tots_i = int(tots)

		if self._epg_cache is None:
			self._epg_cache = {}
			try:
				data = self.cp.tvh.api_get(
					"api/epg/events/grid",
					{"limit": 999999, "sort": "start", "dir": "ASC"}
				) or {}
				entries = data.get("entries") or []
			except Exception:
				entries = []

			for ev in entries:
				try:
					cuuid = ev.get("channelUuid")
					if not cuuid:
						continue
					start = int(ev.get("start") or 0)
					stop = int(ev.get("stop") or 0)
					if not start or not stop:
						continue
					if stop <= fromts_i or start >= tots_i:
						continue
					self._epg_cache.setdefault(cuuid, []).append(ev)
				except Exception:
					continue

		for ev in self._epg_cache.get(ch_uuid, []):
			try:
				start = int(ev.get("start") or 0)
				stop = int(ev.get("stop") or 0)

				title = (self._pick(ev.get("title")) or '').strip()
				desc = (self._pick(ev.get("description")) or self._pick(ev.get("summary")) or '').strip()

				if not title:
					continue

				yield {"start": start, "end": stop, "title": title, "desc": desc}
			except Exception:
				continue
