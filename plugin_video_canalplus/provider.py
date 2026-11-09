# -*- coding: utf-8 -*-
#
# Canal+ (SK/CZ) - live channels, archive (catch-up), userbouquet and XML EPG.
# Sign-in by code via connect.canalplus.com (see canalplus_api.py).

import sys
import base64
from hashlib import md5
from time import time, strftime, localtime

from tools_archivczsk.contentprovider.extended import (ModuleContentProvider, CPModuleLiveTV,
                                                       CPModuleArchive, CPModuleTemplate)
from tools_archivczsk.string_utils import _I, _C
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.generator.lamedb import channel_name_normalise

from .canalplus_api import (CanalplusApi, CanalplusSessionError, USER_AGENT, error_text,
                            event_details, new_user_key_id, ADDON_BUILD)
from .bouquet import CanalplusBouquetXmlEpgGenerator

# the channel list is fetched at most once per this interval
CHANNELS_CACHE_SECONDS = 600

# how far the DVR (catch-up) window reaches and how long a block is in the fallback archive listing
ARCHIVE_HOURS = 168         # 7 days
ARCHIVE_BLOCK_SECONDS = 30 * 60

# PlayReady CDM in tools_cenc needs Python 3; on Python 2.7 playback goes via Widevine (Solocoo)
is_py2 = sys.version_info[0] == 2

# picon/logo size (LogoUrl contains the {resolutionXY} placeholder)
LOGO_SIZE = '220x220'


# ##################################################################################################################

def _flag(value):
	"""Flag from the API, which sends it either as the string 'true' or as a bool."""
	return value in (True, 'true', 'True', 1, '1')


def logo_url(url):
	if not url:
		return None
	return url.replace('{resolutionXY}', LOGO_SIZE)


class CanalplusChannel(object):
	__slots__ = ('key', 'id', 'name', 'picon', 'lcn', 'dvr', 'no_access', 'adult', 'epg_id',
	             'epg_name', 'epg_desc', 'epg_img', 'epg_start', 'epg_stop')

	def __init__(self, key, cid, name, picon=None, lcn=None, dvr=False, no_access=False, adult=False):
		self.key = key          # EpgId as string
		self.id = cid           # numeric id for the bouquet
		self.name = name
		self.picon = picon
		self.lcn = lcn
		self.dvr = dvr
		self.no_access = no_access
		self.adult = adult
		self.epg_id = key
		self.epg_name = None
		self.epg_desc = None
		self.epg_img = None
		self.epg_start = None
		self.epg_stop = None


# ##################################################################################################################

class CanalplusModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider, categories=False)

	def get_live_tv_channels(self, cat_id=None):
		try:
			self.cp.load_channel_list()
			self.cp.load_epg(self.cp.channels)
		except CanalplusSessionError:
			self.cp.session_expired()
			return

		enable_adult = self.cp.get_setting('enable_adult')
		enable_download = self.cp.get_setting('download_live')

		for channel in self.cp.channels:
			if not enable_adult and channel.adult:
				continue

			title = channel.name
			if channel.lcn:
				title = '%d. %s' % (channel.lcn, title)
			if channel.no_access:
				title = _C('grey', title)

			if channel.epg_name:
				epg_str = '  ' + _I(channel.epg_name)
				plot = '%s - %s' % (self.cp.timestamp_to_str(channel.epg_start),
				                    self.cp.timestamp_to_str(channel.epg_stop))
				if channel.epg_desc:
					plot += '\n' + channel.epg_desc
				info_labels = {'title': channel.epg_name, 'plot': plot, 'adult': channel.adult}
				if channel.epg_start and channel.epg_stop:
					info_labels['duration'] = channel.epg_stop - channel.epg_start
			else:
				epg_str = ''
				info_labels = {'title': channel.name, 'adult': channel.adult}

			menu = self.cp.create_ctx_menu()
			if channel.dvr and self.cp.archive_module:
				menu.add_menu_item(self.cp._("Archive"),
				                   cmd=self.cp.archive_module.get_archive_days_for_channels,
				                   channel_id=channel.key, archive_hours=ARCHIVE_HOURS)

			img = channel.epg_img or channel.picon

			self.cp.add_video(title + epg_str, img, info_labels, menu=menu, download=enable_download,
			                  cmd=self.cp.get_live_stream,
			                  channel_key=channel.key, channel_name=channel.name)


# ##################################################################################################################

class CanalplusModuleArchive(CPModuleArchive):

	def __init__(self, content_provider):
		CPModuleArchive.__init__(self, content_provider)

	def get_archive_channels(self):
		try:
			self.cp.load_channel_list()
		except CanalplusSessionError:
			self.cp.session_expired()
			return

		enable_adult = self.cp.get_setting('enable_adult')

		for channel in self.cp.channels:
			if not enable_adult and channel.adult:
				continue

			if channel.dvr and not channel.no_access:
				self.add_archive_channel(channel.name, channel.key, ARCHIVE_HOURS, img=channel.picon,
				                         info_labels={'adult': channel.adult})

	def get_archive_program(self, channel_id, archive_day):
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		channel = self.cp.channels_by_key.get(channel_id)
		channel_name = channel.name if channel else ''
		adult = channel.adult if channel else False

		try:
			events = self.cp.api.get_epg_range(channel_id, ts_from, ts_to)
		except Exception as e:
			self.cp.show_error(self.cp._("Failed to load the TV guide: %s") % error_text(e))
			return

		now = int(time())
		oldest = now - ARCHIVE_HOURS * 3600

		# when a day is opened, the schedule including full programme descriptions is fetched from Solocoo
		if self.cp.api.solocoo.is_paired():
			try:
				if self.cp.api.fetch_solocoo_channel(channel_id, ts_from - 3600, ts_to + 3600):
					events = self.cp.api.get_epg_range(channel_id, ts_from, ts_to)
			except Exception as e:
				self.cp.log_error('Solocoo schedule failed: %s' % error_text(e))

		if not events:
			# for days without a stored schedule, time blocks are offered instead
			self.archive_time_blocks(channel_id, channel_name, ts_from, ts_to, now, adult=adult)
			return

		for ev in events:
			start = ev['start']
			stop = ev['end'] or start
			name = ev['title'] or ''
			if ev.get('subtitle'):
				name = '%s - %s' % (name, ev['subtitle'])

			title = '%s - %s - %s' % (self.cp.timestamp_to_str(start),
			                          self.cp.timestamp_to_str(stop), _I(name))

			info_labels = {'title': ev['title'] or name, 'plot': event_details(ev), 'adult': adult}
			if start and stop:
				info_labels['duration'] = stop - start
			if start > now or stop <= oldest:
				# not broadcast yet or already outside the archive window
				self.cp.add_video(_C('grey', title), ev.get('image'), info_labels, download=False, cmd=self.cp.noop)
				continue

			self.cp.add_video(title, ev.get('image'), info_labels, cmd=self.get_archive_stream,
			                  channel_id=channel_id, start=start, stop=stop,
			                  archive_title='%s - %s' % (channel_name, name))

	def archive_time_blocks(self, channel_id, channel_name, ts_from, ts_to, now,
	                        block=ARCHIVE_BLOCK_SECONDS, adult=False):
		"""Fallback archive listing by time blocks when there is no schedule for the day.

		Shows only blocks that already passed and are still inside the DVR window (ARCHIVE_HOURS)."""
		oldest = now - ARCHIVE_HOURS * 3600
		start = (int(ts_from) // block) * block
		count = 0

		while start < ts_to:
			stop = start + block
			if stop > now:
				break
			if stop > oldest:
				title = '%s - %s' % (self.cp.timestamp_to_str(start),
				                     self.cp.timestamp_to_str(stop))
				info_labels = {'title': '%s %s' % (channel_name, title), 'duration': block, 'adult': adult}
				self.cp.add_video(title, None, info_labels, cmd=self.get_archive_stream,
				                  channel_id=channel_id, start=start, stop=stop,
				                  archive_title='%s %s' % (channel_name, title))
				count += 1
			start = stop

		if not count:
			self.cp.show_info(self.cp._("No TV guide for this day yet. The addon collects "
			                            "the guide daily, so previous days will appear soon."))

	def get_archive_stream(self, channel_id, start, archive_title, stop=None):
		return self.cp.play_asset(channel_id, archive_title, live=False, begin=start, end=stop)

	# --- shortcut to the archive from the receiver EPG / userbouquet ------------------------------

	def _archive_channel(self, channel_key):
		try:
			self.cp.load_channel_list()
		except Exception:
			return None
		channel = self.cp.channels_by_key.get(channel_key)
		return channel if channel and channel.dvr and not channel.no_access else None

	def get_archive_hours(self, channel_id):
		return ARCHIVE_HOURS if self._archive_channel(channel_id) else None

	def get_channel_id_from_path(self, path):
		if not path.startswith(('playlive/', 'playlivets/')):
			return None
		path = path.split('/', 1)[1]
		if path.endswith('/index.mpd'):
			path = path[:-10]
		elif path.endswith('/index'):
			path = path[:-6]
		try:
			channel_key = base64.b64decode(path.encode('utf-8')).decode('utf-8')
		except Exception:
			return None
		return channel_key if self._archive_channel(channel_key) else None

	def get_channel_id_from_sref(self, sref):
		try:
			self.cp.load_channel_list()
		except Exception:
			return None
		name = channel_name_normalise(sref.getServiceName())
		for channel in self.cp.channels:
			if channel.dvr and not channel.no_access and channel_name_normalise(channel.name) == name:
				return channel.key
		return None

	def get_archive_event(self, channel_id, event_start, event_end=None):
		channel = self._archive_channel(channel_id)
		if not channel:
			return
		title = channel.name
		try:
			for ev in self.cp.api.get_epg_range(channel_id, event_start, event_start + 1):
				if ev['start'] <= event_start < (ev['end'] or event_start + 1):
					title = '%s - %s' % (channel.name, ev['title'] or '')
					event_end = event_end or ev['end'] or None
					break
		except Exception:
			pass
		return self.cp.play_asset(channel_id, title, live=False, begin=event_start, end=event_end)


# ##################################################################################################################

class CanalplusModuleExtra(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("Information and settings"))

	def root(self, section=None):
		self.cp.add_dir(self._('Account'), cmd=self.list_account)
		self.cp.add_video(self._("Sign out (pair again)"), cmd=self.sign_out)
		self.cp.add_video(self._("Check playback"), cmd=self.check_playback)
		self.cp.add_video(self._("Run EPG export to enigma or XML files"), cmd=self.export_epg)

	def export_epg(self):
		self.cp.bxeg.refresh_xmlepg_start(True)
		self.cp.show_info(self._("EPG export started"), noexit=True)

	def sign_out(self):
		self.cp.sign_out()
		self.cp.show_info(self._("Signed out. Please exit the addon and open it again to pair."))

	def list_account(self):
		try:
			self.cp.load_channel_list()
		except Exception as e:
			self.cp.show_error(self._("Failed to load account: %s") % error_text(e))
			return

		self.cp.add_video(self._("Zone: %s") % self.cp.api.brand, None, {}, download=False, cmd=self.cp.noop)
		self.cp.add_video(self._("Number of channels: %d") % len(self.cp.channels),
		                  None, {}, download=False, cmd=self.cp.noop)
		if self.cp.widevine_wanted():
			drm = self._("Widevine, SD (this receiver has Python 2.7)")
		else:
			drm = self._("PlayReady, Full HD")
		self.cp.add_video(self._("Playback: %s") % drm, None, {}, download=False, cmd=self.cp.noop)

	def check_playback(self):
		try:
			self.cp.load_channel_list()
		except Exception as e:
			self.cp.show_error(self._("Playback failed: %s") % error_text(e))
			return

		channel = None
		for ch in self.cp.channels:
			if not ch.no_access:
				channel = ch
				break
		if not channel:
			self.cp.show_error(self._("No playable channel found."))
			return

		try:
			stream = self.cp.get_stream_info(channel.key)
		except Exception as e:
			self.cp.show_error(self._("Playback failed: %s") % error_text(e))
			return

		# the check doesn't play anything - close the Broadpeak session right away
		self.cp.api.teardown(stream.get('teardown'))
		self.cp.play_session = {}

		if stream.get('url') and (stream.get('license_url') or self.cp.api.live_token):
			self.cp.show_info(self._("No error occured during playback check. Playback should work."))
		else:
			self.cp.show_error(self._("The server did not return a stream or a license token."))


# ##################################################################################################################

class CanalplusContentProvider(ModuleContentProvider):

	def __init__(self):
		ModuleContentProvider.__init__(self)

		# the version is taken from addon.xml (via the framework) so the log matches the released version
		self.add_initialised_callback(lambda: self.log_info('Canal+ %s (build %d)' % (self.get_addon_version(), ADDON_BUILD)))

		# the sign-in is stored in data_dir (Solocoo), not in the settings
		self.login_settings_names = ()
		self.login_optional_settings_names = ('brand',)

		self.needs_pairing = False
		self.api = CanalplusApi(self)
		self.channels = []
		self.channels_by_key = {}
		self.channels_next_load_time = 0
		self.checksum = None

		# callbacks of the currently playing Broadpeak session (keepalive/teardown)
		self.play_session = {}

		self.bxeg = CanalplusBouquetXmlEpgGenerator(self)

		self.archive_module = CanalplusModuleArchive(self)

		self.modules = [
			CanalplusModuleLiveTV(self),
			self.archive_module,
			CanalplusModuleExtra(self),
		]

		# after the subscription filter changes, the channel list is reloaded immediately, not after the cache expires
		self.add_setting_change_notifier(['only_subscribed'], self.subscription_filter_changed)

	# ##############################################################################################################

	def subscription_filter_changed(self, name, value):
		self.channels_next_load_time = 0

		# the catalogue only covers a window around the current time - the schedule is stored continuously
		# so the archive has programme titles for past days too
		try:
			self.bgservice.run_in_loop('loop(epg)', (int(time()) % 1800) + 5400, self.collect_epg)
		except Exception:
			pass

	# ##############################################################################################################
	# sign-in

	def login(self, silent):
		brand = self.get_setting('brand') or 'cpsvk'
		user_key_id = (self.get_setting('user_key_id') or '').strip()
		if not user_key_id:
			user_key_id = new_user_key_id()
			self.set_setting('user_key_id', user_key_id)

		self.api.setup(brand, user_key_id)

		self.channels = []
		self.channels_by_key = {}
		self.channels_next_load_time = 0
		self.checksum = None

		# without pairing the menu offers sign-in by code
		if not self.api.solocoo.is_paired():
			self.needs_pairing = True
			return True

		self.needs_pairing = False
		try:
			self.api.ensure_pass_token(force=True)
		except CanalplusSessionError as e:
			self.log_info('Saved sign-in is no longer valid: %s' % error_text(e))
			self.needs_pairing = True
			return True
		except Exception as e:
			self.log_error('Login error: %s' % error_text(e))
			self.login_error(self._("Sign-in failed: %s") % error_text(e))
			return False

		return True

	def root(self):
		if self.needs_pairing:
			self.add_video(self._("Sign in with a code (pairing)"), cmd=self.start_pairing)
			return
		for module in self.modules:
			module.add()

	def start_pairing(self):
		"""Sign-in by code via connect.canalplus.com - used for both the schedule and playback."""
		try:
			code, url = self.api.solocoo.request_pairing()
		except Exception as e:
			self.log_error('Pairing error: %s' % error_text(e))
			self.show_error(self._("Could not get a pairing code: %s") % error_text(e))
			return

		sso = None
		msg = self._("Sign in with a code:\n\n"
		             "1) On your phone/PC open %s\n"
		             "2) Sign in and enter this code:\n\n        %s\n\n"
		             "Waiting for confirmation... (press Back to cancel)") % (url, code)
		interval = max(3, self.api.solocoo.pairing_interval())
		for i in range(80):
			if self.show_info(msg, noexit=True, timeout=interval) == False:
				self.log_info('Pairing canceled by user')
				return
			try:
				sso = self.api.solocoo.poll_pairing_once(code)
			except Exception as e:
				self.log_debug('Pairing check failed: %s' % error_text(e))
				sso = None
			if sso:
				break

		if sso:
			self.needs_pairing = False
			try:
				self.api.ensure_pass_token(force=True)
			except Exception as e:
				self.log_error('Sign-in after pairing failed: %s' % error_text(e))
			self.show_info(self._("Paired. Please exit the addon and open it again."))
		else:
			self.show_error(self._("Pairing was not confirmed in time. Please try again."))

	def forget_session(self):
		self.api.pass_token = None
		self.api.pass_token_time = 0

	def sign_out(self):
		self.forget_session()
		try:
			self.api.solocoo.logout()
		except Exception:
			pass
		self.needs_pairing = True

	def session_expired(self):
		self.forget_session()
		self.login_error(self._("Your sign-in has expired."))

	def noop(self):
		return

	def logged_in(self):
		return self.api.logged_in()

	# ##############################################################################################################
	# channels

	def timestamp_to_str(self, timestamp, format_str='%H:%M'):
		if not timestamp:
			return ''
		return strftime(format_str, localtime(timestamp))

	def load_channel_list(self, force=False):
		if not force and self.channels and int(time()) < self.channels_next_load_time:
			return

		raw = self.api.channels()
		only_subscribed = bool(self.get_setting('only_subscribed'))

		channels = []
		by_key = {}
		used_ids = set()
		skipped = 0

		for item in raw:
			key = item.get('EpgId')
			name = item.get('Name')
			if not key or not name:
				continue

			# channel outside the subscription (the server sends it, but it can't be played) - skip according to the setting
			if only_subscribed and _flag((item.get('AccessRights') or {}).get('NoAccess')):
				skipped += 1
				continue

			try:
				lcn = int(item.get('Nb') or item.get('NumZap') or 0)
			except Exception:
				lcn = 0

			cid = lcn if lcn and lcn not in used_ids else None
			if cid is None:
				cid = 10000 + len(channels)
			used_ids.add(cid)

			access = item.get('AccessRights') or {}
			no_access = _flag(access.get('NoAccess'))
			# Cat5Access marks adult (category V) channels, the name prefix is a fallback
			adult = _flag(access.get('Cat5Access')) or name.startswith('(18+)')

			channel = CanalplusChannel(
				key=str(key), cid=cid, name=name,
				picon=logo_url(item.get('LogoUrl')),
				lcn=lcn or None,
				dvr=_flag(item.get('DVR')),
				no_access=no_access,
				adult=adult,
			)
			channels.append(channel)
			by_key[channel.key] = channel

		channels.sort(key=lambda c: (c.lcn or 99999, c.name))
		self.log_debug('Channels: %d from server, %d usable, %d outside subscription' % (len(raw), len(channels), skipped))

		self.channels = channels
		self.channels_by_key = by_key
		self.channels_next_load_time = int(time()) + CHANNELS_CACHE_SECONDS

		# checksum of the channel offer for the bouquet export
		self.checksum = md5(('%s|' % ADDON_BUILD + '|'.join(c.key for c in channels)).encode('utf-8')).hexdigest()

	def load_epg(self, channels):
		"""Adds the currently running programme (title, time, description, thumbnail) to the channels."""
		now = int(time())
		todo = [ch for ch in channels
		        if not ch.epg_name or not ch.epg_stop or ch.epg_stop < now]
		if not todo:
			return

		try:
			epg = self.api.get_epg_now_many([ch.epg_id for ch in todo], now)
		except Exception as e:
			self.log_error('Failed to load the EPG: %s' % error_text(e))
			return

		# descriptions of the currently running programmes from Solocoo
		now_desc = {}   # epg_id -> description
		if self.api.solocoo.is_paired():
			try:
				cc_to_epg = {}
				for ch in todo:
					cc_to_epg[self.api.solocoo_cc_id(ch.epg_id)] = str(ch.epg_id)
				now_map = self.api.solocoo.get_schedule_now(list(cc_to_epg.keys()))
				id_by_epg = {}
				for cc, e in now_map.items():
					eid = cc_to_epg.get(cc)
					if eid and e.get('id'):
						id_by_epg[eid] = e['id']
				desc_map = self.api.solocoo.get_descriptions(list(id_by_epg.values()), time_limit=15)
				for eid, aid in id_by_epg.items():
					d = desc_map.get(aid)
					if d:
						now_desc[eid] = d
			except Exception as e:
				self.log_error('Solocoo descriptions failed: %s' % error_text(e))

		for channel in todo:
			ev = epg.get(str(channel.epg_id))
			if not ev:
				continue
			channel.epg_name = ev.get('title') or None
			channel.epg_start = ev.get('start')
			channel.epg_stop = ev.get('end')
			channel.epg_img = ev.get('image')
			d = now_desc.get(str(channel.epg_id))
			if d and not ev.get('desc'):
				ev['desc'] = d
			channel.epg_desc = event_details(ev) or None

	def get_channel_epg(self, channel_key, time_from, time_to):
		"""Channel schedule for the bouquet and XML EPG - downloaded from the server for the whole range."""
		self.api.fetch_solocoo_channel(channel_key, time_from, time_to, with_desc=False)
		return self.api.get_epg_range(channel_key, time_from, time_to)

	def collect_epg(self):
		"""Downloads and stores the schedule of all channels in the background (Solocoo history + spyro)."""
		try:
			if not self.logged_in():
				return
			self.load_channel_list()
			ids = [ch.epg_id for ch in self.channels if ch.epg_id]
			if not ids:
				return
			try:
				self.api.fetch_solocoo_epg(self.channels)
			except Exception as e:
				self.log_error('Solocoo schedule failed: %s' % error_text(e))
			self.api.get_epg_now_many(ids)
			self.log_debug('EPG collected for %d channels' % len(ids))
		except Exception as e:
			self.log_error('EPG collection failed: %s' % error_text(e))

	# ##############################################################################################################
	# playback

	def stream_headers(self):
		return {
			'User-Agent': USER_AGENT,
			'Origin': 'https://www.canalplus.com',
			'Referer': 'https://www.canalplus.com/',
		}

	def get_dash_info(self, stream_key):
		"""Data for DashHTTPRequestHandler - manifest and license configuration."""
		headers = self.stream_headers()
		license_headers = dict(headers)
		license_headers['Content-Type'] = 'application/json'

		if stream_key.get('wv'):
			# fallback path via Solocoo Widevine (Python 2.7)
			wv_headers = self.api.solocoo.stream_headers()
			wv_license_headers = dict(wv_headers)
			wv_license_headers['Content-Type'] = 'application/octet-stream'
			return {
				'url': stream_key['url'],
				'bandwidth': stream_key.get('bandwidth'),
				'headers': wv_headers,
				'drm': {
					'wv': {
						'license_url': stream_key['wv'],
						'headers': wv_license_headers,
					}
				}
			}

		ctx = stream_key.get('license') or {}

		return {
			'url': stream_key['url'],
			'bandwidth': stream_key.get('bandwidth'),
			'headers': headers,
			'drm': {
				'pr': {
					'license_url': ctx.get('url', ''),
					'headers': license_headers,
					'canalplus': ctx,
				}
			}
		}

	def widevine_wanted(self):
		"""Python 3 = PlayReady (Full HD), Python 2.7 = Widevine via Solocoo (SD) - decided automatically."""
		return is_py2

	def solocoo_asset_for(self, channel_key, begin=None, end=None):
		"""Solocoo id for playback: live channel = cc<EpgId>, archive = programme id from the schedule."""
		if begin is None:
			return self.api.solocoo_cc_id(channel_key)
		t_from = int(begin)
		t_to = int(end) if end else t_from + 1
		events = self.api.get_epg_range(channel_key, t_from, t_to) or []
		best = None
		for ev in events:
			if not ev.get('id'):
				continue
			if best is None or abs(int(ev['start']) - t_from) < abs(int(best['start']) - t_from):
				best = ev
		if best is None:
			# the schedule isn't downloaded yet - try to fetch it and search again
			try:
				self.api.fetch_solocoo_channel(channel_key, t_from - 3600, t_to + 3600, with_desc=False)
			except Exception:
				self.log_exception()
			for ev in self.api.get_epg_range(channel_key, t_from, t_to) or []:
				if ev.get('id') and (best is None or abs(int(ev['start']) - t_from) < abs(int(best['start']) - t_from)):
					best = ev
		return best['id'] if best else None

	def get_stream_info_wv(self, channel_key, begin=None, end=None):
		"""Manifest and Widevine license from Solocoo (no keepalive session)."""
		if not self.api.solocoo.is_paired():
			raise CanalplusSessionError('Not paired')
		asset_id = self.solocoo_asset_for(channel_key, begin, end)
		if not asset_id:
			raise Exception('No programme found for this time in the archive')
		stream = self.api.solocoo.get_stream(asset_id)
		if stream.get('url'):
			self.log_info('Widevine stream from: %s' % (stream['url'].split('/')[2] if stream['url'].count('/') >= 2 else '?'))
		self.play_session = {}
		return stream

	def get_stream_info(self, channel_key, begin=None, end=None):
		"""Returns the manifest URL and license context - also used by the HTTP handler for the bouquet."""
		channel = self.channels_by_key.get(channel_key)
		if not channel:
			self.load_channel_list()
			channel = self.channels_by_key.get(channel_key)
		if not channel:
			raise Exception('Unknown channel')

		if self.widevine_wanted():
			return self.get_stream_info_wv(channel_key, begin=begin, end=end)

		raw = None
		for item in self.api.channels():
			if str(item.get('EpgId')) == channel_key:
				raw = item
				break
		if not raw:
			raise Exception('Channel not in current list')

		stream = self.api.get_stream(raw, live=(begin is None), begin=begin, end=end)

		mpd_url = stream.get('url') or ''
		if mpd_url:
			self.log_info('Stream from: %s' % (mpd_url.split('/')[2] if mpd_url.count('/') >= 2 else '?'))

		# remember the session callbacks - stats() uses them for keepalive and teardown
		self.play_session = {
			'keepalive': stream.get('keepalive'),
			'teardown': stream.get('teardown'),
		}

		return stream

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		"""Keeps the Broadpeak session alive and closes it properly when playback ends.

		Without keepalive the CDN terminates the session after a while (the stream drops),
		without teardown sessions stay open and pile up when switching channels."""
		try:
			session = self.play_session or {}
			if action in ('play', 'watching', 'unpause', 'seek'):
				self.api.keepalive(session.get('keepalive'))
			elif action == 'end':
				self.api.teardown(session.get('teardown'))
				self.play_session = {}
		except Exception:
			self.log_exception()

	def get_live_stream(self, channel_key, channel_name=''):
		return self.play_asset(channel_key, channel_name, live=True)

	def play_asset(self, channel_key, stream_title='', live=True, begin=None, end=None):
		if not channel_key:
			self.show_error(self._("Missing item identifier."))
			return

		try:
			stream = self.get_stream_info(channel_key, begin=begin, end=end)
		except CanalplusSessionError:
			self.session_expired()
			return
		except Exception as e:
			msg = error_text(e)
			self.log_error('Stream error: %s' % msg)
			low = msg.lower()
			if 'noaccess' in low or 'subscri' in low or 'entitle' in low:
				self.show_error(self._("This channel is not part of your subscription."))
			elif 'geo' in low:
				self.show_error(self._("The broadcast is not available from this network (geoblocking)."))
			else:
				self.show_error(self._("Playback failed: %s") % msg)
			return

		mpd_url = stream.get('url') or ''
		if not mpd_url:
			self.show_error(self._("No stream URL received from server."))
			return

		if stream.get('license_url'):
			# Widevine path (Solocoo)
			if not self.resolve_dash_streams_wv(stream, stream_title or stream.get('title') or '', live):
				self.show_error(self._("Failed to load the DASH stream."))
			return

		if not self.api.live_token:
			self.show_error(self._("No license token received. The stream cannot be played."))
			return

		if not self.resolve_dash_streams(stream, stream_title or stream.get('title') or '', live):
			self.show_error(self._("Failed to load the DASH stream."))

	def limit_streams(self, streams):
		try:
			max_height = int(self.get_setting('max_resolution') or 0)
		except Exception:
			max_height = 0
		if not max_height or not streams:
			return streams
		allowed = [s for s in streams if s.get('height') and int(s['height']) <= max_height]
		if not allowed:
			allowed = [min(streams, key=lambda x: int(x.get('height') or 0) or 99999)]
		return allowed

	def resolve_streams_for_channel(self, manifest_url):
		streams = self.get_dash_streams(manifest_url, headers=self.stream_headers(),
		                                max_bitrate=self.get_setting('max_bitrate'))
		return self.limit_streams(streams)

	def resolve_dash_streams_wv(self, stream, title, live):
		"""Widevine (Solocoo): with L3 keys Canal+ delivers SD regardless of the track in the manifest,
		so a single item (the highest allowed track) labelled as SD is offered."""
		streams = self.get_dash_streams(stream['url'], headers=self.api.solocoo.stream_headers(),
		                                max_bitrate=self.get_setting('max_bitrate'))
		streams = self.limit_streams(streams)
		if not streams:
			return False
		s = max(streams, key=lambda x: int(x.get('bandwidth') or 0))
		stream_key = {
			'url': s['playlist_url'],
			'bandwidth': s['bandwidth'],
			'wv': stream.get('license_url') or '',
		}
		url = stream_key_to_dash_url(self.http_endpoint, stream_key)
		info_labels = {
			'bandwidth': int(s['bandwidth']),
			'quality': 'SD (Widevine)',
		}
		self.add_play(title, url, info_labels=info_labels, live=live)
		return True

	def resolve_dash_streams(self, stream, title, live):
		streams = self.resolve_streams_for_channel(stream['url'])
		if not streams:
			return False

		license_ctx = stream.get('license') or {}

		for s in streams:
			stream_key = {
				'url': s['playlist_url'],
				'bandwidth': s['bandwidth'],
				'license': license_ctx,
			}
			url = stream_key_to_dash_url(self.http_endpoint, stream_key)

			info_labels = {
				'bandwidth': int(s['bandwidth']),
				'quality': s['height'] + 'p' if s.get('height') else 'max',
			}
			self.add_play(title, url, info_labels=info_labels, live=live)

		return True
