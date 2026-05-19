# -*- coding: utf-8 -*-
"""
M3URefreshManager - high-level orchestrator that runs the full
fetch -> parse -> apply mapping -> write bouquet -> picons -> epgimport
pipeline. Designed to be called from addon.py either on demand (menu)
or via an eTimer at a configured refresh interval.

Python 2.7 + Python 3.x compatible.
"""

from __future__ import absolute_import, unicode_literals, print_function

import os
import io
import gzip
import time
import threading

try:
	import lzma  # Py3
except ImportError:
	try:
		from backports import lzma
	except ImportError:
		lzma = None

try:
	from .m3u_provider import M3UProvider
	from .m3u_bouquet import M3UBouquetWriter, cleanup_m3u_bouquet, \
		DEFAULT_BOUQUET_DIR, DEFAULT_PICON_DIR, DEFAULT_EPGIMPORT_DIR, \
		M3U_BOUQUET_PREFIX, \
		build_url_to_sref_from_bouquet  # FIX 0.48h
	from .m3u_mapping import M3UMappingOverride
	try:
		from .m3u_tvh_enricher import enrich_with_tvh, derive_tvh_xmltv_url
	except ImportError:
		enrich_with_tvh = None
		derive_tvh_xmltv_url = None
	try:
		from .m3u_epg_injector import inject_epg_into_enigma
	except ImportError:
		inject_epg_into_enigma = None
	try:
		from .m3u_tvh_auth import (parse_tvh_url, build_token_client_from_url,
		                            fetch_tvh_tags_via_url)
	except ImportError:
		parse_tvh_url = None
		build_token_client_from_url = None
		fetch_tvh_tags_via_url = None
except (ValueError, ImportError):
	# Standalone import (test or scripted use outside the plugin package)
	from m3u_provider import M3UProvider
	from m3u_bouquet import M3UBouquetWriter, cleanup_m3u_bouquet, \
		DEFAULT_BOUQUET_DIR, DEFAULT_PICON_DIR, DEFAULT_EPGIMPORT_DIR, \
		build_url_to_sref_from_bouquet
	from m3u_mapping import M3UMappingOverride
	try:
		from m3u_tvh_enricher import enrich_with_tvh, derive_tvh_xmltv_url
	except ImportError:
		enrich_with_tvh = None
		derive_tvh_xmltv_url = None
	try:
		from m3u_epg_injector import inject_epg_into_enigma
	except ImportError:
		inject_epg_into_enigma = None
	try:
		from m3u_tvh_auth import (parse_tvh_url, build_token_client_from_url,
		                          fetch_tvh_tags_via_url)
	except ImportError:
		parse_tvh_url = None
		build_token_client_from_url = None
		fetch_tvh_tags_via_url = None


try:
	# FIX 0.48j: persistent data dir helper
	from ._paths import data_path
except (ValueError, ImportError):
	from _paths import data_path


# FIX 0.48j: stampy v persistent data dir-u (nie v /tmp — prežijú reboot)
_STAMP_FILE = data_path('m3u_last_refresh.stamp')
# FIX 0.48g: separátny stamp pre EPG injection (analógia s
# _EPG_INJECT_STAMP v TVH bouquet.py). Zapisuje sa po každej úspešnej
# direct injection — či už cez refresh_now() alebo cez inject_epg_only().
_EPG_INJECT_STAMP_M3U = data_path('m3u_epg_inject.stamp')
_LOCK = threading.Lock()


class M3URefreshManager(object):
	"""
	Orchestrates an end-to-end refresh of the M3U source.

	settings dict expected keys (all values may also be str-typed):
	    enable_m3u_source        bool
	    m3u_url                  str
	    m3u_epg_url              str
	    m3u_service_type         str        '1' / '4097' / '5001' / '5002'
	    m3u_bouquet_name         str
	    m3u_bouquet_prefix       str        slug for filenames
	    m3u_refresh_interval     int        seconds (0 = manual only)
	    m3u_picons_from_logo     bool
	    m3u_use_mapping          bool
	    m3u_mapping_file         str        path to override XML
	    m3u_bouquet_dir          str        default /etc/enigma2
	    m3u_picon_dir            str        default /usr/share/enigma2/picon
	    m3u_epgimport_dir        str        default /etc/epgimport
	    m3u_write_epgimport      bool
	"""

	def __init__(self, settings_getter, log=None, tvh_client=None):
		"""
		settings_getter: callable(key, default=None) -> value
		  (so caller can pass any framework-specific accessor)
		log: print-like callable
		tvh_client: optional Tvheadend instance (from tvheadend.py).
		  If provided, M3U channels whose URLs point to TVH will be
		  enriched with TVH tags (for group-title) and UUIDs (for tvg-id).
		"""
		self._get = settings_getter
		self.log = log or (lambda *a, **k: None)
		self._tvh = tvh_client
		self._timer = None
		self._stop = False

	# ------------------ Helper accessors ------------------

	def _bool(self, key, default=False):
		v = self._get(key, default)
		if isinstance(v, bool):
			return v
		if isinstance(v, str):
			return v.strip().lower() in ('1', 'true', 'yes', 'on')
		return bool(v)

	def _str(self, key, default=''):
		v = self._get(key, default)
		return '' if v is None else str(v).strip()

	def _int(self, key, default=0):
		try:
			return int(self._get(key, default))
		except (TypeError, ValueError):
			return default

	# ------------------ Public API ------------------

	def is_enabled(self):
		return self._bool('enable_m3u_source', False)

	def can_run(self):
		return self.is_enabled() and bool(self._str('m3u_url'))

	def refresh_now(self):
		"""
		Run a refresh synchronously (blocking). Safe to call from a
		manager thread or eTimer callback. Re-entrancy guarded by lock.
		"""
		# Py2/3 compatible: pass blocking flag positionally
		# (kwarg name is 'blocking' in both, but C impl in Py2.7 quirks)
		acquired = _LOCK.acquire(False)
		if not acquired:
			self.log('[M3U-mgr] refresh already in progress, skipping')
			return False
		try:
			return self._do_refresh()
		finally:
			try:
				_LOCK.release()
			except Exception:
				pass

	def refresh_async(self):
		"""Fire-and-forget refresh on a background thread."""
		t = threading.Thread(target=self.refresh_now, name='M3URefresh')
		t.daemon = True
		t.start()
		return t

	def cleanup(self):
		"""
		Remove generated bouquet + epgimport files and cancel any
		scheduled timer. Called when user disables M3U source in settings.
		Idempotent: safe to call repeatedly.
		"""
		# Cancel timer first so a queued refresh doesn't fight us
		self.cancel()
		bouquet_dir = self._str('m3u_bouquet_dir') or DEFAULT_BOUQUET_DIR
		epgimport_dir = self._str('m3u_epgimport_dir') or DEFAULT_EPGIMPORT_DIR
		# FIX 0.48f: prefix už nie je configurable setting — hardcoded
		prefix = M3U_BOUQUET_PREFIX
		try:
			stats = cleanup_m3u_bouquet(
				bouquet_prefix=prefix,
				bouquet_dir=bouquet_dir,
				epgimport_dir=epgimport_dir,
				log=self.log,
			)
			self.log('[M3U-mgr] cleanup done: %s' % stats)
			return stats
		except Exception as e:
			self.log('[M3U-mgr] cleanup failed: %s' % e)
			return None

	# ------------------ Core ------------------

	def _do_refresh(self):
		if not self.can_run():
			self.log('[M3U-mgr] disabled or URL empty, skipping')
			return False

		start = time.time()

		# Auto-derive EPG URL from TVH if user did not set one explicitly
		epg_url = self._str('m3u_epg_url')
		if not epg_url and self._bool('m3u_enrich_from_tvh', True):
			# Path 1: primary TVH client (full credentials)
			if self._tvh is not None and derive_tvh_xmltv_url is not None:
				try:
					epg_url = derive_tvh_xmltv_url(self._tvh) or ''
				except Exception:
					epg_url = ''

			# Path 2: derive directly from M3U URL using auth token
			# (works even without TVH credentials in plugin settings)
			if not epg_url and parse_tvh_url is not None:
				m3u_url_str = self._str('m3u_url')
				base, token = parse_tvh_url(m3u_url_str)
				if base:
					epg_url = base + '/xmltv/channels'
					if token:
						epg_url += '?auth=' + token

			if epg_url:
				self.log('[M3U-mgr] auto-using TVH XMLTV: %s' % epg_url)

		provider = M3UProvider(
			m3u_url=self._str('m3u_url'),
			epg_url=epg_url,
			log=self.log,
		)
		try:
			provider.fetch_and_parse(fetch_epg=bool(epg_url))
		except Exception as e:
			self.log('[M3U-mgr] fetch/parse failed: %s' % e)
			return False

		# Enrich M3U channels from TVH API (fills tags=group, uuid=tvg-id, icon)
		if (enrich_with_tvh is not None
		        and self._bool('m3u_enrich_from_tvh', True)):

			# Try primary TVH client first (uses host/username/password from settings)
			tvh_client = self._tvh
			primary_ok = False
			if tvh_client is not None:
				try:
					tvh_client.check_login()
					primary_ok = True
				except Exception:
					primary_ok = False

			# Fallback: derive token-only client from M3U URL auth=<token>
			if not primary_ok and build_token_client_from_url is not None:
				m3u_url_str = self._str('m3u_url')
				token_client = build_token_client_from_url(
					m3u_url_str, log=self.log)
				if token_client is not None:
					try:
						token_client.check_login()
						tvh_client = token_client
						self.log('[M3U-mgr] using auth-token TVH client '
						         '(derived from M3U URL)')
					except Exception as e:
						self.log('[M3U-mgr] auth-token fallback failed: %s' % e)
						tvh_client = None

			if tvh_client is not None:
				try:
					enrich_with_tvh(provider, tvh_client, log=self.log)
				except Exception as e:
					self.log('[M3U-mgr] TVH enrichment failed: %s' % e)
			else:
				self.log('[M3U-mgr] no TVH client available, skipping API enrichment')

			# ----- Path 3: URL-based tags via /playlist/tags endpoint -----
			# Aplikuje sa AJ ked predošle enrichment cesty fungovali, ale len pre
			# kanály ktoré skončili v 'Uncategorized'. Použije ten istý auth
			# token ako M3U URL — funguje bez API permissions na tickete.
			uncategorized = sum(1 for ch in provider.get_all_channels()
			                    if (ch.get('group') or '').lower() in
			                       ('', 'uncategorized', 'unknown'))
			if uncategorized > 0 and fetch_tvh_tags_via_url is not None:
				self.log('[M3U-mgr] %d uncategorized channels — trying '
				         'URL-based tag fetch via /playlist/tags' %
				         uncategorized)
				try:
					m3u_url_str = self._str('m3u_url')
					tag_map = fetch_tvh_tags_via_url(m3u_url_str,
					                                  log=self.log)
					if tag_map:
						updated = provider.apply_tag_mapping(tag_map)
						self.log('[M3U-mgr] URL-based tags: assigned tags '
						         'to %d previously uncategorized channels' %
						         updated)
					else:
						self.log('[M3U-mgr] URL-based tags fetch returned '
						         'empty map')
				except Exception as e:
					self.log('[M3U-mgr] URL-based tags fetch failed: %s' % e)

		# Optional mapping override (applied AFTER enrichment so user can
		# rename/reorder the TVH-derived categories)
		if self._bool('m3u_use_mapping'):
			mapping_path = self._str('m3u_mapping_file') or os.path.join(
				DEFAULT_BOUQUET_DIR, 'm3u-sort-override.xml')
			mapper = M3UMappingOverride(path=mapping_path, log=self.log)
			if mapper.load():
				self._apply_mapping_to_provider(provider, mapper)

		# Bouquet writer config
		settings = {
			# FIX 0.48f: bouquet_prefix už nie je configurable, vždy hardcoded
			'bouquet_prefix': M3U_BOUQUET_PREFIX,
			'bouquet_display_name': self._str('m3u_bouquet_name') or 'IPTV M3U',
			'service_type': self._str('m3u_service_type') or '1',
			'add_category_markers': True,
			'bouquet_dir': self._str('m3u_bouquet_dir') or DEFAULT_BOUQUET_DIR,
			'picon_dir': self._str('m3u_picon_dir') or DEFAULT_PICON_DIR,
			'epgimport_dir': self._str('m3u_epgimport_dir') or DEFAULT_EPGIMPORT_DIR,
			'download_picons': self._bool('m3u_picons_from_logo', True),
			# FIX 0.48g: write_epgimport setting odstránený z UI, vždy False.
			# Generation epgimport XML súborov je duplicitná s direct EPG
			# injection ktorý robí to isté efektívnejšie. Pre legacy
			# inštalácie ktoré majú m3u_write_epgimport=true v
			# /etc/enigma2/settings tým túto hodnotu ignorujeme.
			'write_epgimport': False,
			'epg_source_url': epg_url,
			'epg_source_description': 'M3U IPTV (%s)' %
			    self._str('m3u_bouquet_name', 'IPTV'),
		}

		writer = M3UBouquetWriter(provider, settings, log=self.log)
		try:
			writer.run()
		except Exception as e:
			self.log('[M3U-mgr] bouquet write failed: %s' % e)
			return False

		# Direct EPG injection into Enigma2 eEPGCache.
		# This makes EPG appear immediately without requiring the
		# external epgimport plugin to run.
		#
		# FIX 0.48g: gated by m3u_epg_inject_interval > 0 (predtým bool
		# m3u_inject_epg_to_enigma). Bool nahrádza single keyenum
		# kde 0 = Disabled, >0 = interval pre auto-inject mimo bouquet
		# refresh-u. Pri každom bouquet refreshi sa EPG vždy injektuje
		# (ak interval > 0), keďže máme práve čerstvé XMLTV.
		# FIX 0.48h: stats check — stamp len pri reálne >0 events injected
		# (rovnaký vzor ako inject_epg_only, defensive consistency).
		epg_inject_interval = self._int('m3u_epg_inject_interval', 14400)
		if (inject_epg_into_enigma is not None
		        and epg_inject_interval > 0
		        and provider._raw_epg_bytes):
			try:
				# Decompress if needed (XMLTV may arrive gzipped/xz-ed)
				raw = provider._raw_epg_bytes
				if raw[:2] == b'\x1f\x8b':
					raw = gzip.decompress(raw) if hasattr(gzip, 'decompress') \
						else gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
				elif raw[:6] == b'\xfd7zXZ\x00' and lzma is not None:
					raw = lzma.decompress(raw)
				stats = inject_epg_into_enigma(provider, raw, log=self.log)
				events_injected = (stats or {}).get('events_total', 0)
				if events_injected > 0:
					try:
						with open(_EPG_INJECT_STAMP_M3U, 'w') as f:
							f.write(str(int(time.time())))
					except Exception:
						pass
				else:
					self.log('[M3U-mgr] refresh_now: EPG injector returned 0 '
					         'events — not stamping inject success')
			except Exception as e:
				self.log('[M3U-mgr] EPG injection failed: %s' % e)

		# Update timestamp
		try:
			with open(_STAMP_FILE, 'w') as f:
				f.write(str(int(time.time())))
		except Exception:
			pass

		elapsed = time.time() - start
		self.log('[M3U-mgr] Refresh complete in %.1fs '
		         '(%d channels, %d categories)' %
		         (elapsed, provider.channel_count(),
		          len(provider.get_categories())))
		return True

	def inject_epg_only(self):
		"""FIX 0.48g: light-weight EPG-only refresh (bez bouquet rebuild-u).

		Stiahne M3U (potrebné pre tvg_id -> service_ref mapping) + XMLTV,
		injektuje cez eEPGCache. Preskakuje: enrichment, mapping override,
		bouquet write, picon download.

		Použitie: periodický EPG refresh medzi bouquet refresh-ami
		(M3U bouquet typicky 24h interval, EPG 4h interval).

		Vracia: True ak injection prebehla, False pri chybe alebo vypnutom
		feature.

		FIX 0.48h: dva kritické bugy z 0.48g:
		  BUG 1: žiadny kanál nemal '_service_ref' nastavený (to robí len
		    M3UBouquetWriter pri full refresh-i), takže
		    `inject_epg_into_enigma()` postavila prázdnu id_to_ref mapu
		    a injektnula 0 events. Stav: tichý fail, žiadny errror v UI.
		    FIX: pred volaním injektora prečítaj existujúci userbouquet
		    z disku, postav {url: short_sref} mapu, namapuj na channels.
		  BUG 2: stamp `_EPG_INJECT_STAMP_M3U` sa zapisoval AJ KEĎ 0 events
		    boli injektnuté (injector nehadzal exception, len vrátil stats).
		    Auto-retry sa potom odložil o celý interval (typicky 4h).
		    FIX: skontroluj stats.events_total > 0 pred zapísaním stamp.
		"""
		if not self._bool('enable_m3u_source', False):
			return False
		if inject_epg_into_enigma is None:
			self.log('[M3U-mgr] inject_epg_only: injector unavailable')
			return False
		epg_inject_interval = self._int('m3u_epg_inject_interval', 14400)
		if epg_inject_interval <= 0:
			return False

		m3u_url = self._str('m3u_url')
		if not m3u_url:
			return False

		# FIX 0.48h (BUG 1, časť 1): postav url→sref mapu z existujúceho bouquetu
		bouquet_dir = self._str('m3u_bouquet_dir') or DEFAULT_BOUQUET_DIR
		bouquet_path = os.path.join(
			bouquet_dir,
			'userbouquet.{}.tv'.format(M3U_BOUQUET_PREFIX)
		)
		url_to_sref = build_url_to_sref_from_bouquet(bouquet_path)
		if not url_to_sref:
			self.log('[M3U-mgr] inject_epg_only: bouquet %s not found or empty — '
			         'run full M3U refresh first (Settings → Refresh M3U now)' %
			         bouquet_path)
			return False
		self.log('[M3U-mgr] inject_epg_only: loaded %d url→sref mappings '
		         'from existing bouquet' % len(url_to_sref))

		start = time.time()

		# Auto-derive EPG URL — rovnaký vzor ako v refresh_now
		epg_url = self._str('m3u_epg_url')
		if not epg_url and self._bool('m3u_enrich_from_tvh', True):
			if self._tvh is not None and derive_tvh_xmltv_url is not None:
				try:
					epg_url = derive_tvh_xmltv_url(self._tvh) or ''
				except Exception:
					epg_url = ''
			if not epg_url and parse_tvh_url is not None:
				base, token = parse_tvh_url(m3u_url)
				if base:
					epg_url = base + '/xmltv/channels'
					if token:
						epg_url += '?auth=' + token

		if not epg_url:
			self.log('[M3U-mgr] inject_epg_only: no EPG URL available')
			return False

		# Fetch M3U + XMLTV
		try:
			provider = M3UProvider(m3u_url=m3u_url, epg_url=epg_url, log=self.log)
			provider.fetch_and_parse(fetch_epg=True)
		except Exception as e:
			self.log('[M3U-mgr] inject_epg_only: fetch/parse failed: %s' % e)
			return False

		if not provider._raw_epg_bytes:
			self.log('[M3U-mgr] inject_epg_only: empty EPG response')
			return False

		# FIX 0.48h (BUG 1, časť 2): pripoj _service_ref k channels podľa URL
		matched_sref = 0
		for ch in provider._channels:
			url = ch.get('url')
			if url and url in url_to_sref:
				ch['_service_ref'] = url_to_sref[url]
				matched_sref += 1

		if matched_sref == 0:
			self.log('[M3U-mgr] inject_epg_only: 0 channels matched to bouquet '
			         '(URLs changed since bouquet was generated?) — skip')
			return False
		self.log('[M3U-mgr] inject_epg_only: %d/%d channels mapped to '
		         'service refs from bouquet' %
		         (matched_sref, provider.channel_count()))

		# Decompress + inject
		try:
			raw = provider._raw_epg_bytes
			if raw[:2] == b'\x1f\x8b':
				raw = gzip.decompress(raw) if hasattr(gzip, 'decompress') \
					else gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
			elif raw[:6] == b'\xfd7zXZ\x00' and lzma is not None:
				raw = lzma.decompress(raw)
			# FIX 0.48h (BUG 2): skontroluj stats a NEUKLADAJ stamp pri 0 events
			stats = inject_epg_into_enigma(provider, raw, log=self.log)
			events_injected = (stats or {}).get('events_total', 0)
			if events_injected <= 0:
				self.log('[M3U-mgr] inject_epg_only: 0 events injected — NOT '
				         'updating stamp (will retry next watchdog tick)')
				return False
			# Reálny úspech → stamp
			try:
				with open(_EPG_INJECT_STAMP_M3U, 'w') as f:
					f.write(str(int(time.time())))
			except Exception:
				pass
			elapsed = time.time() - start
			self.log('[M3U-mgr] inject_epg_only complete in %.1fs '
			         '(%d events across %d services)' %
			         (elapsed, events_injected,
			          (stats or {}).get('services_total', 0)))
			return True
		except Exception as e:
			self.log('[M3U-mgr] inject_epg_only: injection failed: %s' % e)
			return False

	def _apply_mapping_to_provider(self, provider, mapper):
		"""Rewrite provider's internal channel list using mapping rules."""
		# Filter channels (mutates each channel dict in place)
		kept = []
		for ch in provider._channels:
			if mapper.apply_channel_rule(ch):
				kept.append(ch)
		provider._channels = kept

		# Reorder/filter categories
		src_cats = provider._categories
		ordered = mapper.filter_and_order_categories(src_cats)
		# ordered = [(orig_name, display_name), ...]
		# We need to update channel 'group' if display name differs
		display_map = {orig: disp for orig, disp in ordered}

		# Filter channels to only those whose category is in display_map
		# (handle channels moved via categoryOverride - they may now belong
		# to a category not present in display_map; keep them and create
		# the category at the end)
		final_channels = []
		final_categories = []
		seen_cats = set()

		# Pass 1: emit channels in declared category order
		for orig, disp in ordered:
			for ch in provider._channels:
				if ch['group'] == orig:
					ch['group'] = disp
					final_channels.append(ch)
			if disp not in seen_cats:
				final_categories.append(disp)
				seen_cats.add(disp)

		# Pass 2: orphan channels with overridden categories not in mapping
		for ch in provider._channels:
			if ch not in final_channels:
				if ch['group'] not in seen_cats:
					final_categories.append(ch['group'])
					seen_cats.add(ch['group'])
				final_channels.append(ch)

		provider._channels = final_channels
		provider._categories = final_categories

	# ------------------ Scheduler ------------------

	def schedule(self, etimer_class=None):
		"""
		Start periodic refresh using either an enigma2 eTimer (passed in)
		or a plain Python threading.Timer (fallback for testing).

		FIX 0.48:
		  - Re-entrancy guard: ak už timer beží, nevytvor druhý.
		    Predtým sa pri každom plugin login()-e zavolal `schedule()`
		    a vytvoril sa NOVÝ eTimer/Timer bez zrušenia starého ->
		    paralelné refresh-e + thread leak (na 24/7 boxoch sa to
		    rátalo do desiatok timerov za týždeň).
		  - eTimer.callback: vyčistí pôvodný zoznam pred append-om,
		    aby sa pri prípadnom opakovanom volaní neakumulovali volania.
		  - threading.Timer fallback: nahradený jediným daemon threadom
		    s threading.Event.wait() — žiadny Timer-rebuild leak na
		    každom tiku.
		"""
		interval = self._int('m3u_refresh_interval', 0)
		if interval <= 0:
			self.log('[M3U-mgr] periodic refresh disabled')
			# ak bol predtým nastavený, zruš ho
			self.cancel()
			return

		# Už beží — neduplikuj
		if self._timer is not None:
			self.log('[M3U-mgr] scheduler already running, skipping new schedule()')
			return

		self._stop = False

		if etimer_class is not None:
			# Enigma2 native eTimer
			self._timer = etimer_class()
			# Bezpečné resetnutie callback listu (nie všetky enigma buildy
			# majú stabilný .callback API, preto try/except)
			try:
				del self._timer.callback[:]
			except Exception:
				pass
			try:
				self._timer.callback.append(self.refresh_async)
			except Exception as e:
				self.log('[M3U-mgr] eTimer callback append failed: %s' % e)
				self._timer = None
				return
			try:
				self._timer.start(interval * 1000, False)
				self.log('[M3U-mgr] eTimer scheduled, interval=%ds' % interval)
			except Exception as e:
				self.log('[M3U-mgr] eTimer.start() failed: %s' % e)
				self._timer = None
			return

		# Fallback: jediný daemon thread + Event.wait (žiadne kaskádové Timer-y)
		self._stop_event = threading.Event()

		def _loop():
			while not self._stop_event.wait(interval):
				if self._stop:
					return
				try:
					self.refresh_async()
				except Exception as e:
					self.log('[M3U-mgr] scheduled refresh error: %s' % e)

		t = threading.Thread(target=_loop, name='M3URefreshScheduler')
		t.daemon = True
		t.start()
		self._timer = t  # držíme len handle, riadime cez _stop_event
		self.log('[M3U-mgr] threading scheduler started, interval=%ds' % interval)

	def cancel(self):
		self._stop = True
		ev = getattr(self, '_stop_event', None)
		if ev is not None:
			try:
				ev.set()
			except Exception:
				pass
		if self._timer is not None:
			try:
				if hasattr(self._timer, 'stop'):
					self._timer.stop()
				elif hasattr(self._timer, 'cancel'):
					self._timer.cancel()
				# threading.Thread sa zastaví sám cez _stop_event
			except Exception:
				pass
			self._timer = None


# -------------------------------------------------
# Smoke test
# -------------------------------------------------
if __name__ == '__main__':
	import sys
	if len(sys.argv) < 2:
		print('Usage: m3u_manager.py <m3u_url> [<epg_url>]')
		sys.exit(1)

	cfg = {
		'enable_m3u_source': True,
		'm3u_url': sys.argv[1],
		'm3u_epg_url': sys.argv[2] if len(sys.argv) > 2 else '',
		'm3u_service_type': '1',
		'm3u_bouquet_name': 'IPTV M3U Test',
		'm3u_bouquet_prefix': 'm3u_iptv_test',
		'm3u_bouquet_dir': '/tmp/test_bouquet',
		'm3u_picon_dir': '/tmp/test_picons',
		'm3u_epgimport_dir': '/tmp/test_epgimport',
		'm3u_picons_from_logo': False,
		'm3u_write_epgimport': True,
		'm3u_refresh_interval': 0,
	}
	for d in ('/tmp/test_bouquet', '/tmp/test_picons', '/tmp/test_epgimport'):
		if not os.path.exists(d):
			os.makedirs(d)

	mgr = M3URefreshManager(
		settings_getter=lambda k, d=None: cfg.get(k, d),
		log=print,
	)
	ok = mgr.refresh_now()
	print('Refresh OK:', ok)
