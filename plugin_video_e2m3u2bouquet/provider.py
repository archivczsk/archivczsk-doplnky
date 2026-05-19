# -*- coding: utf-8 -*-
"""
E2M3U2Bouquet content provider — main UI orchestrator pre M3U → Enigma2 bouquet workflow.

Extract z plugin.video.tvheadend 0.57.0 (skyjet PR #22 review #10/#11).
"""

from __future__ import absolute_import, unicode_literals, print_function

import os
import threading

from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import (
	AddonErrorException, AddonInfoException,
)

from .m3u_manager import M3URefreshManager
from .m3u_bouquet import M3U_BOUQUET_PREFIX


# Plugin player_name enum (0-3) → Enigma2 service_type.
# Plugin nastavenie je v antik-style enum (`player_name`); m3u_manager.py
# vnútorne pracuje so service_type string-om, takže provider robí konverziu.
_PLAYER_NAME_TO_SERVICE_TYPE = {
	'0': '4097',  # Default (servicemp3 / default Enigma2 player)
	'1': '5001',  # gstplayer
	'2': '5002',  # exteplayer3
	'3': '1',     # DVB (OE >= 2.5)
}


class E2M3U2BouquetContentProvider(CommonContentProvider):
	"""Hlavný content provider pre M3U → Enigma2 bouquet."""

	name = 'e2m3u2bouquet'

	def __init__(self):
		CommonContentProvider.__init__(self, name=self.name)
		self._m3u_manager = None
		self._m3u_lock = threading.Lock()

		# login_optional_settings_names = framework zavolá login_data_changed()
		# keď user zmení niektoré z týchto settings (re-login auto trigger).
		# NEPOUŽÍVAM login_settings_names — blokuje aj root() pri prázdnych
		# values (plugin sa otvorí úplne prázdny bez info dialogu).
		# Namiesto toho v login() ručne kontrolujem a volám show_info()
		# rovnako ako plugin.video.disneyplus.
		self.login_optional_settings_names = ('m3u_url', 'm3u_epg_url',
		                                       'enable_userbouquet')

	def login(self, silent):
		"""Disneyplus-style login: kontrola required setting + show_info.

		Plus pri každom login init manager + auto-refresh ak je
		enable_userbouquet ON. Framework volá login() pri každom otvorení
		pluginu — pri prvom otvorení s vyplnenou URL sa bouquet vygeneruje
		automaticky.
		"""
		# Disneyplus-style: required settings check + info dialog
		if not (self.get_setting('m3u_url') or '').strip():
			if not silent:
				self.show_info(self._(
				    "To display content, you must enter M3U playlist URL "
				    "in the addon settings"), noexit=True)
			return False

		# Plus auto-refresh ak je enable_userbouquet ON
		mgr = self._maybe_init_m3u_manager()
		if mgr is not None and mgr.is_enabled() and mgr.can_run():
			try:
				mgr.refresh_async()
			except Exception as e:
				try:
					self.log_error('[m3u] auto-refresh on login failed: %s' % e)
				except Exception:
					pass
		return True

	def root(self):
		"""Root menu — kontextové:
		- M3U URL prázdne: hint užívateľovi že treba vyplniť URL cez modré
		  tlačidlo Nastavenia (archivCZSK addon settings UI)
		- M3U URL vyplnené: 'Nastavenia' folder so statusom + manuálnymi
		  akciami (TVH-style sub-menu)
		"""
		m3u_url = (self.get_setting('m3u_url') or '').strip()

		if not m3u_url:
			self.add_dir(
				self._('⚙ M3U URL not configured — open Settings (blue button)'),
				cmd=self.settings_menu,
				info_labels={'title': self._('Configure M3U')})
			return

		self.add_dir(self._('Settings'),
		             cmd=self.settings_menu,
		             info_labels={'title': self._('Settings')})

	def _to_bool(self, v):
		if v is None or v == '':
			return False
		s = str(v).lower()
		return s in ('1', 'true', 'yes', 'on')

	# ------------------------------------------------------------------
	# Settings sub-menu (status + manuálne actions, TVH-style)
	# ------------------------------------------------------------------

	def settings_menu(self):
		"""Nastavenia sub-menu — status info + manuálne actions + diagnostika.

		Štruktúra (TVH style):
		  - Status lines (URL, posledný refresh, EPG age, ...)
		  - Separator
		  - Manuálne actions (Refresh, Inject EPG, Cleanup, ...)
		  - Diagnostika separator
		  - Show paths
		"""
		m3u_url = (self.get_setting('m3u_url') or '').strip()
		enable_userbouquet = self._to_bool(self.get_setting('enable_userbouquet'))

		# --- Status sekcia (vždy) ---
		for line in self._build_status_lines():
			self.add_dir(line, cmd=self.settings_menu,
			             info_labels={'title': line})

		# --- Action sekcia (len ak M3U URL je vyplnená) ---
		if m3u_url:
			self.add_dir('─' * 32, cmd=self.settings_menu,
			             info_labels={'title': self._('M3U Actions')})

			if enable_userbouquet:
				self.add_dir(self._('Refresh M3U playlist + EPG now'),
				             cmd=self.action_m3u_refresh)
				self.add_dir(self._('Refresh M3U playlist (background)'),
				             cmd=self.action_m3u_refresh_async)
				self.add_dir(self._('Inject EPG only (no playlist refresh)'),
				             cmd=self.action_m3u_inject_epg)
			else:
				self.add_dir(self._('⚠ Userbouquet export is disabled in settings'),
				             cmd=self.settings_menu,
				             info_labels={'title': self._('Disabled')})

			# Cleanup (ak existuje bouquet)
			ub_path = '/etc/enigma2/userbouquet.{}.tv'.format(M3U_BOUQUET_PREFIX)
			if os.path.isfile(ub_path):
				self.add_dir(self._('✗ Remove M3U bouquet'),
				             cmd=self.action_m3u_cleanup)

		# --- Diagnostika (vždy) ---
		self.add_dir('─' * 32, cmd=self.settings_menu,
		             info_labels={'title': self._('Diagnostics')})

		self.add_dir(self._('Show paths and generated files'),
		             cmd=self.action_show_paths,
		             info_labels={'title': self._('Paths')})

	def _build_status_lines(self):
		"""Status info pre Settings sub-menu (M3U side)."""
		import time

		lines = []
		m3u_url = (self.get_setting('m3u_url') or '').strip()
		epg_url = (self.get_setting('m3u_epg_url') or '').strip()
		enable_userbouquet = self._to_bool(self.get_setting('enable_userbouquet'))

		def _shorten(u, n=40):
			if not u:
				return '(not set)'
			if len(u) <= n:
				return u
			return u[:n - 15] + '...' + u[-12:]

		# M3U URL
		lines.append('◆ %s: %s' % (self._('M3U URL'), _shorten(m3u_url)))

		# EPG URL
		lines.append('◆ %s: %s' % (self._('XMLTV EPG URL'), _shorten(epg_url)))

		# Master toggle status
		if m3u_url:
			if enable_userbouquet:
				lines.append('◆ %s: %s' % (
					self._('Userbouquet export'), self._('enabled')))
			else:
				lines.append('◆ %s: %s' % (
					self._('Userbouquet export'), self._('disabled')))

		# Last refresh timestamp (z data_path/m3u_last_refresh.stamp)
		try:
			from ._paths import data_path
			stamp = data_path('m3u_last_refresh.stamp')
			if os.path.isfile(stamp):
				age = time.time() - os.path.getmtime(stamp)
				lines.append('◆ %s: %s' % (
					self._('Last M3U refresh'), self._fmt_age(age)))
			elif m3u_url:
				lines.append('◆ %s: %s' % (
					self._('Last M3U refresh'), self._('never')))
		except Exception:
			pass

		# Last EPG inject timestamp (z m3u_epg_inject.stamp)
		try:
			from ._paths import data_path
			stamp = data_path('m3u_epg_inject.stamp')
			if os.path.isfile(stamp):
				age = time.time() - os.path.getmtime(stamp)
				# Plus aj inject interval
				interval_s = int(self.get_setting('m3u_epg_inject_interval') or 0)
				if interval_s > 0:
					if interval_s >= 86400:
						iv = '%dd' % (interval_s // 86400)
					else:
						iv = '%dh' % (interval_s // 3600)
					lines.append('◆ %s: %s (every %s)' % (
						self._('Last EPG inject'), self._fmt_age(age), iv))
				else:
					lines.append('◆ %s: %s' % (
						self._('Last EPG inject'), self._fmt_age(age)))
		except Exception:
			pass

		# Bouquet file presence
		try:
			ub_path = '/etc/enigma2/userbouquet.{}.tv'.format(M3U_BOUQUET_PREFIX)
			if os.path.isfile(ub_path):
				with open(ub_path, 'r') as f:
					content = f.read()
				ch_count = content.count('#SERVICE')
				lines.append('◆ %s: %d channels' % (
					self._('Bouquet file'), ch_count))
		except Exception:
			pass

		return lines

	def _fmt_age(self, age_sec):
		"""Format age in seconds → human readable (e.g. '3h 24m ago')."""
		import time
		try:
			age = int(age_sec)
			if age < 60:
				return '%ds ago' % age
			if age < 3600:
				return '%dm ago' % (age // 60)
			if age < 86400:
				h = age // 3600
				m = (age % 3600) // 60
				return '%dh %dm ago' % (h, m)
			d = age // 86400
			h = (age % 86400) // 3600
			return '%dd %dh ago' % (d, h)
		except Exception:
			return '?'

	def action_show_paths(self):
		"""Zobrazí paths a vygenerované súbory."""
		from ._paths import data_path

		paths = [
			('/etc/enigma2/userbouquet.{}.tv'.format(M3U_BOUQUET_PREFIX),
			 self._('M3U bouquet')),
			(data_path('m3u_last_refresh.stamp'),
			 self._('Last refresh stamp')),
			(data_path('m3u_epg_inject.stamp'),
			 self._('Last EPG inject stamp')),
		]

		lines = []
		for path, label in paths:
			exists = '✓' if os.path.isfile(path) else '✗'
			lines.append('{} {}: {}'.format(exists, label, path))

		raise AddonInfoException('\n'.join(lines))

	def _maybe_init_m3u_manager(self):
		"""Lazy init M3URefreshManager. Vráti instance alebo None."""
		if self._m3u_manager is not None:
			return self._m3u_manager
		with self._m3u_lock:
			if self._m3u_manager is not None:
				return self._m3u_manager
			try:
				def _settings_get(key, default=None):
					try:
						# Mapovanie: m3u_manager očakáva 'm3u_service_type'
						# v string formáte ('1'/'4097'/'5001'/'5002'),
						# plugin setting je v antik-style 'player_name'
						# enum (0-3).
						if key == 'm3u_service_type':
							pn = self.get_setting('player_name') or '0'
							return _PLAYER_NAME_TO_SERVICE_TYPE.get(str(pn), '4097')
						# m3u_manager.is_enabled() volá 'enable_m3u_source'
						# (legacy key z plug TVH 0.56beta). V e2m3u2bouquet
						# 0.1.0 je antik-style key 'enable_userbouquet'.
						if key == 'enable_m3u_source':
							key = 'enable_userbouquet'
						v = self.get_setting(key)
						if v is None or v == '':
							return default
						return v
					except Exception:
						return default

				def _m3u_log(*parts):
					msg = ' '.join(str(p) for p in parts)
					try:
						self.log_info('[m3u] ' + msg)
					except Exception:
						pass

				tvh_client = self._maybe_build_tvh_client()

				self._m3u_manager = M3URefreshManager(
					settings_getter=_settings_get,
					log=_m3u_log,
					tvh_client=tvh_client,
				)

				# Auto-rebuild bouquet keď user zmení niektoré z týchto
				# settings (rovnaký pattern ako framework BouquetXmlEpgGenerator
				# v tools_archivczsk/generator/bouquet_xmlepg.py:158).
				#
				# Plus dôležite: 'player_name' tu zaisťuje že keď user zmení
				# prehrávač (Default/gstplayer/exteplayer3/DMM/DVB), bouquet sa
				# regeneruje so správnym service_type a picons s correct
				# filenames pre Enigma2 lookup.
				try:
					self.add_setting_change_notifier((
						'm3u_url',
						'm3u_epg_url',
						'enable_userbouquet',
						'm3u_bouquet_name',
						'm3u_picons_from_logo',
						'm3u_use_mapping',
						'm3u_mapping_file',
						'm3u_enrich_from_tvh',
						'player_name',
					), self._on_bouquet_settings_changed)
				except Exception:
					# Framework nemusí mať add_setting_change_notifier
					# (staršie verzie) — auto-rebuild bude zlyhať silent
					pass

				return self._m3u_manager
			except Exception as e:
				try:
					self.log_error('[m3u] manager init failed: %s' % e)
				except Exception:
					pass
				return None

	def _on_bouquet_settings_changed(self, *args, **kwargs):
		"""Callback keď user zmení nejaký bouquet-related setting v UI.

		Plus spustí background refresh aby sa bouquet regeneroval s novými
		hodnotami (napr. nový player_name → nový service_type → nové
		picon filenames). M3URefreshManager interne handluje cooldown
		stamp ak refresh prebehol nedávno."""
		try:
			self.log_info('[m3u] bouquet settings changed — triggering refresh')
		except Exception:
			pass

		mgr = self._m3u_manager
		if mgr is None:
			return
		try:
			# Skús async refresh — ak je manager v is_enabled() OFF, no-op
			if mgr.is_enabled() and mgr.can_run():
				mgr.refresh_async()
		except Exception as e:
			try:
				self.log_error('[m3u] settings-change refresh failed: %s' % e)
			except Exception:
				pass

	def _maybe_build_tvh_client(self):
		"""Vráti TVH token client ak M3U URL je TVH URL formátu
		`http://host:port/playlist/auth/?auth=<token>`. Inak None.

		Pre TVH-hostované M3U playlisty extrahuje auth token zo samotného
		URL a vytvorí TvhAuthTokenClient (token-based access, žiadne
		username/password potrebné). Použité pre m3u_tvh_enricher (channel
		tags pre group-title, UUID pre tvg-id).

		Standalone M3U use-case (TVH URL nie je v M3U): vráti None,
		manager beží bez TVH enrichment.
		"""
		try:
			# Toggle settings — user môže explicitne vypnúť TVH enrichment
			enrich = (self.get_setting('m3u_enrich_from_tvh') or '').lower()
			if enrich in ('0', 'false', 'no', 'off'):
				return None

			m3u_url = (self.get_setting('m3u_url') or '').strip()
			if not m3u_url:
				return None

			from .m3u_tvh_auth import build_token_client_from_url

			def _log(*parts):
				try:
					self.log_info('[m3u.tvh] ' + ' '.join(str(p) for p in parts))
				except Exception:
					pass

			return build_token_client_from_url(m3u_url, log=_log)
		except Exception:
			return None

	# ------------------------------------------------------------------

	def action_m3u_refresh(self):
		mgr = self._maybe_init_m3u_manager()
		if mgr is None or not mgr.is_enabled():
			raise AddonInfoException(self._(
				'M3U source is not configured. Open Settings to fill in M3U URL.'))
		try:
			ok = mgr.refresh_now()
			if ok:
				raise AddonInfoException(self._('✓ M3U refresh complete'))
			else:
				raise AddonInfoException(self._(
					'M3U refresh skipped (already running or disabled)'))
		except AddonInfoException:
			raise
		except Exception as e:
			self.log_error('[m3u] refresh failed: %s' % e)
			raise AddonErrorException(self._('M3U refresh failed: {}').format(e))

	def action_m3u_refresh_async(self):
		mgr = self._maybe_init_m3u_manager()
		if mgr is None or not mgr.is_enabled():
			raise AddonInfoException(self._(
				'M3U source is not configured. Open Settings to fill in M3U URL.'))
		mgr.refresh_async()
		raise AddonInfoException(self._('✓ M3U refresh started in background'))

	def action_m3u_inject_epg(self):
		mgr = self._maybe_init_m3u_manager()
		if mgr is None or not mgr.is_enabled():
			raise AddonInfoException(self._(
				'M3U source is not configured. Open Settings to fill in M3U URL.'))
		try:
			result = mgr.inject_epg_only()
			if result:
				raise AddonInfoException(self._('✓ EPG injected'))
			else:
				raise AddonInfoException(self._(
					'EPG injection skipped (no events or bouquet missing)'))
		except AddonInfoException:
			raise
		except Exception as e:
			self.log_error('[m3u] inject EPG failed: %s' % e)
			raise AddonErrorException(self._('EPG injection failed: {}').format(e))

	def action_m3u_cleanup(self):
		mgr = self._maybe_init_m3u_manager()
		if mgr is None:
			# Fallback bez manager-a — manual file delete
			removed = 0
			for fn in [
				'/etc/enigma2/userbouquet.{}.tv'.format(M3U_BOUQUET_PREFIX),
				'/etc/enigma2/userbouquet.{}.radio'.format(M3U_BOUQUET_PREFIX),
			]:
				try:
					if os.path.isfile(fn):
						os.remove(fn)
						removed += 1
				except Exception:
					pass
			try:
				from enigma import eDVBDB
				eDVBDB.getInstance().reloadBouquets()
			except Exception:
				pass
			raise AddonInfoException(
				self._('✓ Removed M3U bouquet files: {}').format(removed))

		try:
			stats = mgr.cleanup()
			if stats:
				raise AddonInfoException(
					self._('✓ M3U cleanup done: {}').format(stats))
			else:
				raise AddonInfoException(self._('Cleanup returned no stats'))
		except AddonInfoException:
			raise
		except Exception as e:
			raise AddonErrorException(self._('Cleanup failed: {}').format(e))
