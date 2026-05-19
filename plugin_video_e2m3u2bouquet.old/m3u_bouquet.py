# -*- coding: utf-8 -*-
"""
M3UBouquetWriter - converts M3UProvider channel data into:
  - userbouquet_*.tv file with fake-DVB (type=1) service refs
  - bouquets.tv inclusion line
  - epgimport channels/sources XML files
  - per-channel picons downloaded from tvg-logo URLs

Service refs use the 'fake DVB' format:
    1:0:1:{SID hex}:{TSID hex}:{ONID hex}:0:0:0:0:{URL}:{Name}

This format makes Enigma2 treat the HTTP stream as a native DVB service,
which enables HW DVB subtitle rendering (unlike 4097/5001/5002 paths).

Python 2.7 + Python 3.x compatible.
"""

from __future__ import absolute_import, unicode_literals, print_function

import os
import io
import re
import hashlib

try:
	from urllib.request import Request, urlopen
	from urllib.parse import quote as urlquote
	from urllib.parse import unquote as urlunquote
except ImportError:
	from urllib2 import Request, urlopen
	from urllib import quote as urlquote
	from urllib import unquote as urlunquote

try:
	basestring
except NameError:
	basestring = (str, bytes)


# Standard Enigma2 paths (some images use /etc/enigma2/, custom builds vary)
DEFAULT_BOUQUET_DIR = '/etc/enigma2'
DEFAULT_PICON_DIR = '/usr/share/enigma2/picon'
DEFAULT_EPGIMPORT_DIR = '/etc/epgimport'

# FIX 0.48f: prefix názvu súboru M3U userbouquetu — predtým configurable
# setting `m3u_bouquet_prefix`, teraz hardcoded. UI tým zostáva čistejšie
# (prefix bol pre 100% userov irelevantný — Enigma2 ho nikdy nezobrazuje,
# je len súčasť názvu súboru na disku). Pre power-users ktorí by chceli
# custom prefix: zmeniť túto konštantu v zdrojáku.
M3U_BOUQUET_PREFIX = 'm3u_iptv'


# FIX 0.48h: build_url_to_sref_from_bouquet — pomocný parser pre existujúci
# userbouquet.<prefix>.tv. Vracia {decoded_url: short_service_ref_with_colon}.
#
# Použité v M3URefreshManager.inject_epg_only(), ktorý NEVYTVÁRA nový bouquet
# (to robí len full refresh) — potrebuje teda namapovať live channels späť na
# service refs zapísané pri minulom bouquet refresh-i, aby ich vedel naviazať
# na XMLTV programmy v eEPGCache.
def build_url_to_sref_from_bouquet(bouquet_path):
	"""Parsuje existujúci userbouquet.<prefix>.tv. Vráti dict
	{decoded_stream_url: short_service_ref_with_trailing_colon}.

	Vynechá kategoriálne markery (1:64:...). Vráti {} ak súbor neexistuje
	alebo nemá žiadne stream entries.

	Short sref formát: '1:0:1:sid:tsid:onid:0:0:0:0:' — taký aký očakáva
	eEPGCache.importEvent() (prvých 10 polí + trailing ':').
	"""
	out = {}
	if not bouquet_path or not os.path.isfile(bouquet_path):
		return out
	try:
		with io.open(bouquet_path, 'r', encoding='utf-8') as f:
			for line in f:
				if not line.startswith('#SERVICE '):
					continue
				sref_full = line[len('#SERVICE '):].strip()
				parts = sref_full.split(':')
				# Markery nemajú stream URL — skip
				if len(parts) < 11:
					continue
				if parts[1] == '64':  # marker type
					continue
				# Polia 0..9 = standard service ref, pole 10 = encoded URL,
				# pole 11+ = názov kanála (môže obsahovať ':').
				short_sref = ':'.join(parts[:10]) + ':'
				url_encoded = parts[10]
				if not url_encoded:
					continue
				try:
					url_decoded = urlunquote(url_encoded)
				except Exception:
					url_decoded = url_encoded
				if url_decoded:
					out[url_decoded] = short_sref
	except Exception:
		# pri akejkoľvek chybe nech vráti čo má, alebo prázdne
		pass
	return out


def _atomic_write(path, data, mode='w', encoding='utf-8'):
	"""Write file atomically via temp + rename."""
	tmp = path + '.tmp'
	if 'b' in mode:
		with open(tmp, mode) as f:
			f.write(data)
	else:
		with io.open(tmp, mode, encoding=encoding) as f:
			f.write(data)
	if hasattr(os, 'replace'):
		os.replace(tmp, path)
	else:  # py2
		if os.path.exists(path):
			os.remove(path)
		os.rename(tmp, path)


def _safe_filename(s):
	"""Make a string safe for use as a filename slug."""
	if not isinstance(s, basestring):
		s = str(s)
	if isinstance(s, bytes):
		s = s.decode('utf-8', errors='ignore')
	s = re.sub(r'[^A-Za-z0-9_\-]+', '_', s.strip().lower())
	return s.strip('_') or 'bouquet'


def _e2_url_encode(url):
	"""
	Encode URL for inclusion in an E2 service ref string.

	The service ref uses ':' as field separator, so ':' MUST be encoded.
	'/' is safe to leave as-is (E2 does not use it as separator).
	'?', '&', '=' are encoded for parity with e2m3u2bouquet output
	(its bouquets are proven to work with DVB-subtitle path).
	"""
	return urlquote(url, safe='/')


def _ns_for_category(category_name):
	"""
	Deterministic TSID + ONID from category name.
	Stable across refreshes => stable picon naming.

	Vracia UPPERCASE hex (zhodne s framework tools_archivczsk.generator.bouquet
	`build_service_ref` ktorý používa `{:X}` format). Enigma2 picon engine
	hľadá súbor s rovnakým case ako service ref → caps zaisťuje match.
	"""
	h = hashlib.md5(category_name.encode('utf-8')).hexdigest()
	tsid_hex = h[0:4].upper()
	onid_hex = h[4:8].upper()
	return tsid_hex, onid_hex


class M3UBouquetWriter(object):
	"""
	Renders an M3UProvider into Enigma2 bouquet + picon + EPG files.
	"""

	def __init__(self, provider, settings, log=None):
		"""
		settings: dict-like with keys:
		    bouquet_prefix          (str)   e.g. 'm3u_iptv'  -> userbouquet_m3u_iptv.tv
		    bouquet_display_name    (str)   shown in E2 menu
		    service_type            (str)   '1' / '4097' / '5001' / '5002'
		    add_category_markers    (bool)  insert category separators
		    bouquet_dir             (str)   default /etc/enigma2
		    picon_dir               (str)   default /usr/share/enigma2/picon
		    epgimport_dir           (str)   default /etc/epgimport
		    download_picons         (bool)
		    picon_format            (str)   'png' (default)
		    write_epgimport         (bool)
		    epg_source_url          (str)   public URL for sources.xml (can equal provider.epg_url)
		    epg_source_description  (str)
		"""
		self.provider = provider
		self.s = settings
		self.log = log or (lambda *a, **k: None)

	# ------------------ Service ref building ------------------

	def _build_service_ref(self, idx, channel, category_name):
		stype = str(self.s.get('service_type', '1')).strip() or '1'
		sid_hex = format(idx, 'X')   # UPPERCASE hex (zhodne s framework)
		tsid_hex, onid_hex = _ns_for_category(category_name)

		# Build URL for stream. If channel has custom headers (User-Agent
		# from #EXTVLCOPT), we *cannot* encode those into the service ref;
		# they would need a proxy script. Log a warning if present.
		if channel.get('_extra_headers'):
			self.log('[M3U] WARN: channel "%s" has custom HTTP headers '
			         '(User-Agent/Referer) that E2 cannot pass directly; '
			         'consider a stream-proxy.' % channel['name'])

		url_encoded = _e2_url_encode(channel['url'])

		# Some E2 builds also need ':' in the name escaped; replace with ' '
		safe_name = (channel['name'] or '').replace(':', ' ').replace('\n', ' ')

		ref = '{stype}:0:1:{sid}:{tsid}:{onid}:0:0:0:0:{url}:{name}'.format(
			stype=stype, sid=sid_hex, tsid=tsid_hex, onid=onid_hex,
			url=url_encoded, name=safe_name,
		)
		return ref

	def _build_category_marker(self, category_idx, category_name):
		"""
		Category separator line (greyed-out marker in bouquet list).
		Format: 1:64:{idx hex}:0:0:0:0:0:0:0::{Name}
		"""
		safe_name = (category_name or '').replace(':', ' ').replace('\n', ' ')
		return '1:64:{:x}:0:0:0:0:0:0:0::{}'.format(category_idx, safe_name)

	# ------------------ Bouquet file ------------------

	def write_bouquet(self):
		# FIX 0.48f: bouquet_prefix sa už nečíta zo settings (UI cleanup) —
		# vždy hardcoded constant M3U_BOUQUET_PREFIX. self.s.get(...) ostáva
		# pre prípad že caller explicitne pošle override, inak fallback.
		prefix = self.s.get('bouquet_prefix') or M3U_BOUQUET_PREFIX
		prefix = _safe_filename(prefix)
		display_name = (self.s.get('bouquet_display_name')
		                or 'IPTV M3U').strip()

		bouquet_dir = self.s.get('bouquet_dir', DEFAULT_BOUQUET_DIR)
		add_markers = bool(self.s.get('add_category_markers', True))

		if not os.path.isdir(bouquet_dir):
			raise RuntimeError('Bouquet dir does not exist: %s' % bouquet_dir)

		filename = 'userbouquet.{}.tv'.format(prefix)
		path = os.path.join(bouquet_dir, filename)

		lines = []
		lines.append('#NAME {}'.format(display_name))

		idx = 1
		for cat_idx, cat in enumerate(self.provider.get_categories()):
			chs = self.provider.get_channels_by_category(cat)
			if not chs:
				continue

			if add_markers:
				lines.append('#SERVICE ' + self._build_category_marker(cat_idx, cat))
				lines.append('#DESCRIPTION ' + cat)

			for ch in chs:
				ref = self._build_service_ref(idx, ch, cat)
				ch['_service_ref'] = ref       # remember for picon/epg use
				lines.append('#SERVICE ' + ref)
				lines.append('#DESCRIPTION ' + (ch['name'] or ''))
				idx += 1

		_atomic_write(path, '\n'.join(lines) + '\n')
		self.log('[M3U] Wrote bouquet: %s (%d channels)' % (path, idx - 1))

		# Update bouquets.tv to include our bouquet
		self._ensure_bouquet_included(bouquet_dir, filename, display_name)

		return path

	def _ensure_bouquet_included(self, bouquet_dir, filename, display_name):
		"""Add our userbouquet to bouquets.tv if not already there.
		If already present, refresh the #DESCRIPTION line so renaming the
		bouquet in settings actually changes the name shown in the E2 menu.
		"""
		bq_index = os.path.join(bouquet_dir, 'bouquets.tv')
		ref_line = ('#SERVICE 1:7:1:0:0:0:0:0:0:0:'
		            'FROM BOUQUET "{}" ORDER BY bouquet'.format(filename))
		desc_line = '#DESCRIPTION ' + display_name

		try:
			with io.open(bq_index, 'r', encoding='utf-8') as f:
				content = f.read()
		except IOError:
			content = '#NAME Bouquets (TV)\n'

		lines = content.rstrip().split('\n')

		# Find our #SERVICE line (match by filename, the rest may differ
		# slightly across images - quotes, ORDER BY, whitespace).
		svc_idx = -1
		for i, ln in enumerate(lines):
			if ln.startswith('#SERVICE ') and filename in ln:
				svc_idx = i
				break

		if svc_idx == -1:
			# Not present yet - append both lines at the end.
			lines.append(ref_line)
			lines.append(desc_line)
			_atomic_write(bq_index, '\n'.join(lines) + '\n')
			self.log('[M3U] Added to bouquets.tv: %s (name="%s")'
			         % (filename, display_name))
			return

		# Already present - make sure the following #DESCRIPTION matches
		# the current display_name (this is what E2 shows in the bouquet
		# list). Without this, renaming in settings has no visible effect.
		changed = False
		if (svc_idx + 1 < len(lines)
		        and lines[svc_idx + 1].startswith('#DESCRIPTION')):
			if lines[svc_idx + 1] != desc_line:
				lines[svc_idx + 1] = desc_line
				changed = True
		else:
			# #SERVICE without #DESCRIPTION - insert one.
			lines.insert(svc_idx + 1, desc_line)
			changed = True

		if changed:
			_atomic_write(bq_index, '\n'.join(lines) + '\n')
			self.log('[M3U] Updated bouquets.tv #DESCRIPTION for %s -> "%s"'
			         % (filename, display_name))

	# ------------------ Picon download ------------------

	def _picon_filename_from_ref(self, service_ref):
		"""
		E2 picon naming convention (matches openatv/openpli):
		Replace ':' with '_', take first 10 fields (drop URL+name).
		Toto je Service Reference Pattern (SRP).

		DÔLEŽITÉ: NEROBIŤ .lower() — Enigma2 `getPiconName` (OpenATV
		`Picon.py`) hľadá súbor s rovnakým case ako je v service ref:
		`fields = serviceName.split(":", 10)[:10]; "_".join(fields)`.
		Service ref vždy obsahuje CAPS hex (`533B`, `3DD2`) — picon
		filename musí mať tiež CAPS aby Enigma2 ho našla.
		"""
		fields = service_ref.split(':')
		# Service ref structure: type:flags:stype:sid:tsid:onid:ns:p1:p2:p3:url:name
		# Picon uses fields 0..9 = type, flags, stype, sid, tsid, onid, ns, p1, p2, p3
		picon_fields = fields[:10]
		key = '_'.join(picon_fields)
		return key + '.png'

	def download_picons(self):
		"""Stiahne picony cez SRP-only (service reference) cestu.

		Skyjet PR #22 review #8: SNP cesta odstránená — picons sa ukladajú
		LEN ako `<service_ref>.png` (napr. `5002_0_1_174_B366_1_7070000_0_0_0.png`),
		nie ako `<channel_name_slug>.png` (napr. `beatv.png`). SNP cesta by
		prepisovala picons iných providerov.

		OpenATV/OpenPLI skiny default-uje hľadať picons SRP-first, SNP-fallback.
		Pre M3U bouquet generovaný týmto plugin-om sú SRP picons dostatočné."""
		if not bool(self.s.get('download_picons', True)):
			return
		picon_dir = self.s.get('picon_dir', DEFAULT_PICON_DIR)
		if not os.path.isdir(picon_dir):
			try:
				os.makedirs(picon_dir)
			except Exception as e:
				self.log('[M3U] Cannot create picon dir %s: %s' % (picon_dir, e))
				return

		downloaded = 0
		skipped = 0
		failed = 0
		for ch in self.provider.get_all_channels():
			ref = ch.get('_service_ref')
			logo = ch.get('tvg_logo')
			if not ref or not logo:
				continue

			srp_name = self._picon_filename_from_ref(ref)
			srp_path = os.path.join(picon_dir, srp_name)

			# Skip ak picon už existuje
			if os.path.exists(srp_path) and os.path.getsize(srp_path) > 0:
				skipped += 1
				continue

			try:
				req = Request(logo)
				req.add_header('User-Agent',
				               'Mozilla/5.0 (Enigma2) M3UProvider/1.0')
				resp = urlopen(req, timeout=15)
				try:
					data = resp.read()
				finally:
					try:
						resp.close()
					except Exception:
						pass

				if not data or len(data) < 100:
					failed += 1
					continue

				tmp = srp_path + '.tmp'
				with open(tmp, 'wb') as f:
					f.write(data)
				if hasattr(os, 'replace'):
					os.replace(tmp, srp_path)
				else:
					if os.path.exists(srp_path):
						os.remove(srp_path)
					os.rename(tmp, srp_path)
				downloaded += 1
			except Exception as e:
				failed += 1
				self.log('[M3U] Picon download failed for %s: %s' %
				         (ch['name'], e))

		self.log('[M3U] Picons (SRP-only): downloaded=%d skipped=%d failed=%d'
		         % (downloaded, skipped, failed))

	# ------------------ epgimport integration ------------------

	def write_epgimport_files(self):
		"""
		Generate two files for the epgimport plugin:
		  /etc/epgimport/<prefix>.channels.xml
		  /etc/epgimport/<prefix>.sources.xml
		"""
		if not bool(self.s.get('write_epgimport', True)):
			return None
		if not self.s.get('epg_source_url'):
			self.log('[M3U] No EPG source URL configured; skipping epgimport export')
			return None

		epgimport_dir = self.s.get('epgimport_dir', DEFAULT_EPGIMPORT_DIR)
		if not os.path.isdir(epgimport_dir):
			try:
				os.makedirs(epgimport_dir)
			except Exception as e:
				self.log('[M3U] Cannot create epgimport dir: %s' % e)
				return None

		# FIX 0.48f: hardcoded M3U_BOUQUET_PREFIX
		prefix = _safe_filename(self.s.get('bouquet_prefix') or M3U_BOUQUET_PREFIX)
		channels_file = '{}.channels.xml'.format(prefix)
		sources_file = '{}.sources.xml'.format(prefix)

		# --- channels.xml ---
		channels_path = os.path.join(epgimport_dir, channels_file)
		lines = ['<channels>']
		total_entries = 0
		for ch in self.provider.get_all_channels():
			ref = ch.get('_service_ref')
			if not ref:
				continue
			# epgimport wants 'name:type:flags:stype:sid:tsid:onid:ns:p1:p2:p3:'
			# i.e. first 10 fields + trailing ':' (no URL/name)
			ref_no_url = ':'.join(ref.split(':')[:10]) + ':'

			# Collect ALL possible tvg-id aliases (set by enricher)
			ids_to_write = set()
			primary = (ch.get('tvg_id') or '').strip()
			if primary:
				ids_to_write.add(primary)
			aliases = ch.get('_tvg_id_aliases') or set()
			if aliases:
				ids_to_write.update(aliases)

			if not ids_to_write:
				continue  # no tvg-id, no EPG mapping possible

			for tvg in ids_to_write:
				if not tvg:
					continue
				tvg_esc = (tvg.replace('&', '&amp;').replace('<', '&lt;')
				              .replace('>', '&gt;').replace('"', '&quot;'))
				lines.append('  <channel id="{}">{}</channel>'.format(
					tvg_esc, ref_no_url))
				total_entries += 1
		lines.append('</channels>')
		_atomic_write(channels_path, '\n'.join(lines) + '\n')
		self.log('[M3U] channels.xml: %d entries written (multi-alias)' %
		         total_entries)

		# --- sources.xml ---
		sources_path = os.path.join(epgimport_dir, sources_file)
		desc = self.s.get('epg_source_description') or 'M3U IPTV EPG'
		src_url = self.s.get('epg_source_url')
		src_lines = [
			'<sources>',
			'  <sourcecat sourcecatname="M3U IPTV">',
			'    <source type="gen_xmltv" channels="{}">'.format(channels_file),
			'      <description>{}</description>'.format(desc),
			'      <url><![CDATA[{}]]></url>'.format(src_url),
			'    </source>',
			'  </sourcecat>',
			'</sources>',
		]
		_atomic_write(sources_path, '\n'.join(src_lines) + '\n')

		self.log('[M3U] Wrote epgimport files: %s, %s' %
		         (channels_path, sources_path))
		return (channels_path, sources_path)

	# ------------------ One-shot orchestration ------------------

	def run(self):
		"""Convenience: write bouquet + picons + epgimport in one call."""
		self.write_bouquet()
		try:
			self.download_picons()
		except Exception as e:
			self.log('[M3U] Picon stage failed: %s' % e)
		try:
			self.write_epgimport_files()
		except Exception as e:
			self.log('[M3U] EPG import stage failed: %s' % e)

		# Force Enigma2 to re-read bouquet files from disk so that the
		# new #NAME and channel list show up immediately without restart.
		self._reload_enigma_bouquets()

	def _reload_enigma_bouquets(self):
		"""
		Tell Enigma2 to re-read bouquet files from disk.

		Without this, Enigma2 keeps the cached bouquet list in memory
		(loaded at startup) and the new #NAME/channels we just wrote
		won't appear until next enigma restart.

		Tries multiple reload mechanisms (some images expose different APIs):
		  1. eDVBDB.reloadBouquets()  - primary, C++ API
		  2. eDVBDB.reloadServicelist() - secondary, refreshes service cache
		  3. OpenWebif /web/servicelistreload - HTTP fallback
		"""
		# Path 1: eDVBDB.reloadBouquets() — standard C++ API
		try:
			from enigma import eDVBDB
		except ImportError:
			# Not running inside Enigma2 (e.g. tests)
			return
		try:
			db = eDVBDB.getInstance()
			db.reloadBouquets()
			self.log('[M3U] eDVBDB.reloadBouquets() OK')
			# Bonus: also reload service list if available (some skins/images
			# cache the bouquet display names in serviceCenter)
			try:
				db.reloadServicelist()
				self.log('[M3U] eDVBDB.reloadServicelist() OK')
			except Exception:
				pass
		except Exception as e:
			self.log('[M3U] eDVBDB.reloadBouquets() failed: %s' % e)

		# Path 2: OpenWebif HTTP endpoint - works regardless of skin caching
		try:
			# mode=2 reloads bouquets and userbouquets
			resp = urlopen('http://127.0.0.1/web/servicelistreload?mode=2',
			               timeout=5)
			try:
				resp.read()
			finally:
				try:
					resp.close()
				except Exception:
					pass
			self.log('[M3U] OpenWebif servicelistreload OK')
		except Exception as e:
			# OpenWebif may not be running or on different port
			self.log('[M3U] OpenWebif servicelistreload skipped: %s' % e)


# -------------------------------------------------
# Cleanup helper (callable without an M3UBouquetWriter instance)
# -------------------------------------------------
def cleanup_m3u_bouquet(bouquet_prefix=None,
                        bouquet_dir=DEFAULT_BOUQUET_DIR,
                        epgimport_dir=DEFAULT_EPGIMPORT_DIR,
                        log=None):
	"""
	Remove a previously generated M3U bouquet from the system. Idempotent —
	safe to call even when nothing exists yet.

	FIX 0.48f: bouquet_prefix default je teraz None — fallne na konštantu
	M3U_BOUQUET_PREFIX. Caller môže poslať explicitný prefix ak chce
	vyčistiť legacy bouquet s iným prefixom.

	Steps:
	  1. Strip our #SERVICE + following #DESCRIPTION lines from bouquets.tv
	  2. Delete /etc/enigma2/userbouquet.<prefix>.tv
	  3. Delete /etc/epgimport/<prefix>.channels.xml and .sources.xml
	  4. Reload Enigma2 bouquet/service list (best effort)

	Returns dict with stats {bouquets_tv_updated, userbouquet_deleted,
	epgimport_deleted, reloaded}.
	"""
	log = log or (lambda *a, **k: None)
	prefix = _safe_filename(bouquet_prefix or M3U_BOUQUET_PREFIX)
	filename = 'userbouquet.{}.tv'.format(prefix)
	stats = {
		'bouquets_tv_updated': False,
		'userbouquet_deleted': False,
		'epgimport_deleted': 0,
		'reloaded': False,
	}

	# ----- 1. Strip from bouquets.tv -----
	bq_index = os.path.join(bouquet_dir, 'bouquets.tv')
	try:
		with io.open(bq_index, 'r', encoding='utf-8') as f:
			content = f.read()
	except IOError:
		content = ''

	if content:
		lines = content.rstrip().split('\n')
		out_lines = []
		i = 0
		removed = 0
		while i < len(lines):
			ln = lines[i]
			# Drop any #SERVICE line that references our filename, and
			# the immediately following #DESCRIPTION (if any).
			if ln.startswith('#SERVICE ') and filename in ln:
				removed += 1
				i += 1
				if i < len(lines) and lines[i].startswith('#DESCRIPTION'):
					i += 1
				continue
			out_lines.append(ln)
			i += 1

		if removed:
			try:
				_atomic_write(bq_index, '\n'.join(out_lines) + '\n')
				stats['bouquets_tv_updated'] = True
				log('[M3U-cleanup] Removed %d entry/entries for %s from bouquets.tv'
				    % (removed, filename))
			except Exception as e:
				log('[M3U-cleanup] bouquets.tv update failed: %s' % e)

	# ----- 2. Delete userbouquet file -----
	ub_path = os.path.join(bouquet_dir, filename)
	if os.path.isfile(ub_path):
		try:
			os.remove(ub_path)
			stats['userbouquet_deleted'] = True
			log('[M3U-cleanup] Deleted %s' % ub_path)
		except Exception as e:
			log('[M3U-cleanup] Cannot delete %s: %s' % (ub_path, e))

	# ----- 3. Delete epgimport channels/sources -----
	for suffix in ('.channels.xml', '.sources.xml'):
		p = os.path.join(epgimport_dir, prefix + suffix)
		if os.path.isfile(p):
			try:
				os.remove(p)
				stats['epgimport_deleted'] += 1
				log('[M3U-cleanup] Deleted %s' % p)
			except Exception as e:
				log('[M3U-cleanup] Cannot delete %s: %s' % (p, e))

	# ----- 4. Reload Enigma2 (best effort) -----
	if stats['bouquets_tv_updated'] or stats['userbouquet_deleted']:
		try:
			from enigma import eDVBDB
			db = eDVBDB.getInstance()
			db.reloadBouquets()
			try:
				db.reloadServicelist()
			except Exception:
				pass
			stats['reloaded'] = True
			log('[M3U-cleanup] Enigma2 bouquets reloaded')
		except ImportError:
			pass  # not running on Enigma2 (tests)
		except Exception as e:
			log('[M3U-cleanup] eDVBDB reload failed: %s' % e)

		# OpenWebif fallback
		try:
			resp = urlopen('http://127.0.0.1/web/servicelistreload?mode=2',
			               timeout=5)
			try:
				resp.read()
			finally:
				try:
					resp.close()
				except Exception:
					pass
			stats['reloaded'] = True
		except Exception:
			pass

	return stats


# -------------------------------------------------
# Standalone smoke test
# -------------------------------------------------
if __name__ == '__main__':
	import sys
	from m3u_provider import M3UProvider

	if len(sys.argv) < 2:
		print('Usage: m3u_bouquet.py <m3u_url> [<epg_url>]')
		sys.exit(1)

	m3u_url = sys.argv[1]
	epg_url = sys.argv[2] if len(sys.argv) > 2 else None

	p = M3UProvider(m3u_url=m3u_url, epg_url=epg_url, log=print)
	p.fetch_and_parse()

	settings = {
		'bouquet_prefix': 'm3u_iptv_test',
		'bouquet_display_name': 'IPTV M3U Test',
		'service_type': '1',
		'add_category_markers': True,
		'bouquet_dir': '/tmp/test_bouquet',
		'picon_dir': '/tmp/test_picons',
		'epgimport_dir': '/tmp/test_epgimport',
		'download_picons': False,  # set True to actually fetch logos
		'write_epgimport': True,
		'epg_source_url': epg_url,
	}
	for d in (settings['bouquet_dir'], settings['picon_dir'],
	          settings['epgimport_dir']):
		if not os.path.exists(d):
			os.makedirs(d)

	w = M3UBouquetWriter(p, settings, log=print)
	w.run()
	print('Done. Inspect /tmp/test_bouquet/userbouquet.m3u_iptv_test.tv')
