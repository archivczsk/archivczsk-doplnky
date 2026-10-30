# -*- coding: utf-8 -*-
#
# Skylink Live TV pre ArchivCZSK - slovenská aj česká verzia.
#
# Službu (SK/CZ) a prihlasovacie údaje zadáš v nastaveniach doplnku. Prihlásenie
# je obyčajné meno a heslo, bez captchy. Zariadenie sa zaregistruje raz a jeho
# identifikátor sa uloží, aby doplnok nezaberal nové zariadenie pri každom štarte.
#
# Doplnok vie živé vysielanie, archív, export do userbouquetu a XML EPG,
# rovnako ako ostatné doplnky s živým vysielaním.

import base64
import sys
from time import time, strftime, localtime
from hashlib import md5
from binascii import crc32

from tools_archivczsk.contentprovider.extended import (ModuleContentProvider, CPModuleLiveTV,
                                                       CPModuleArchive, CPModuleTemplate)
from tools_archivczsk.string_utils import _I, _C
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.generator.lamedb import channel_name_normalise

from .skylink_api import (SkylinkApi, SkylinkSessionError, BRANDS, USER_AGENT, error_text,
                          channel_id as asset_channel_id, channel_title, unwrap_asset,
                          to_timestamp, event_description, image_url,
                          ADDON_VERSION, ADDON_BUILD)
from .bouquet import SkylinkBouquetXmlEpgGenerator

# zoznam kanálov ťaháme najviac raz za tento čas
CHANNELS_CACHE_SECONDS = 600

# server neprijme program za rozsah dlhší než jeden deň
ARCHIVE_WINDOW = 24 * 3600

# knižnica pre PlayReady v tools_cenc vyžaduje Python 3, pod Python 2 ide len Widevine
is_py2 = (sys.version_info[0] == 2)

# koľko kanálov sa pýtame na program jedným volaním a koľko najviac naraz
EPG_BATCH = 20
EPG_MAX_CHANNELS = 400

# popis relácie sa ťahá zvlášť, paralelne; viac než toľko položiek naraz nemá zmysel
DESCRIPTION_LIMIT = 400

# rozmer náhľadu relácie - bez neho server vráti originál, ktorý prijímač nenačíta
PREVIEW_WIDTH = 256
PREVIEW_HEIGHT = 144

# preklad žánrových skupín z API na čitateľné názvy
GENRE_NAMES = {
	'Movie/TV Series': 'Movies and series',
	'Sport': 'Sport',
	'Factual': 'Documentary',
	'News': 'News',
	'Kids': 'Kids',
	'Entertainment': 'Entertainment',
	'Cookery': 'Cooking',
	'Leisure': 'Lifestyle',
	'Music': 'Music',
	'Culture': 'Culture',
	'Adult': 'Adult',
}


# ##################################################################################################################

def asset_image(asset, prefer='la', width=0, height=0):
	"""Vyberie obrázok položky - uprednostní zadaný typ."""
	images = asset.get('images') or []
	chosen = None
	for img in images:
		if not isinstance(img, dict) or not img.get('url'):
			continue
		if img.get('type') == prefer:
			return image_url(img['url'], width, height)
		if chosen is None:
			chosen = img['url']
	return image_url(chosen, width, height)


class SkylinkChannel(object):
	__slots__ = ('key', 'id', 'name', 'picon', 'adult', 'archive', 'lcn', 'radio',
	             'replay_delay', 'epg_id', 'epg_name', 'epg_desc', 'epg_img',
	             'epg_start', 'epg_stop', 'epg_full_desc')

	def __init__(self, key, cid, name, picon=None, adult=False, archive=0, lcn=None):
		self.key = key          # identifikátor položky v API
		self.id = cid           # číselné id pre bouquet a EPG
		self.name = name
		self.picon = picon
		self.adult = adult
		self.archive = archive  # hodiny archívu
		self.lcn = lcn
		self.radio = False
		self.replay_delay = 0
		self.epg_id = None
		self.epg_name = None
		self.epg_desc = None
		self.epg_img = None
		self.epg_start = None
		self.epg_stop = None
		self.epg_full_desc = False  # popis je zo servera, nie poskladaný


# ##################################################################################################################

class SkylinkModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider, categories=True)

	def get_live_tv_categories(self):
		try:
			self.cp.load_channel_list()
		except SkylinkSessionError:
			self.cp.session_expired()
			return

		self.add_live_tv_category(self.cp._("All channels"), 'all')

		for channel in self.cp.channels:
			if channel.radio:
				self.add_live_tv_category(self.cp._("Radio"), 'radio')
				break

		enable_adult = self.cp.get_setting('enable_adult')

		try:
			groups = self.cp.api.get_channel_groups()
		except SkylinkSessionError:
			self.cp.session_expired()
			return
		except Exception as e:
			self.cp.log_error('Failed to load genres: %s' % error_text(e))
			groups = []

		for group in groups:
			key = group.get('key') or ''
			query = group.get('query')
			if not query:
				continue
			if key == 'Adult' and not enable_adult:
				# inak by sa kategória otvorila prázdna, kanály sa aj tak odfiltrujú
				continue
			if key in GENRE_NAMES:
				title = self.cp._(GENRE_NAMES[key])
			else:
				label = (group.get('label') or '').split('.')[-1].replace('_', ' ')
				title = label or key or query
			self.add_live_tv_category(title, query)

	def get_live_tv_channels(self, cat_id=None):
		# session môže vypršať aj neskôr - zoznam kanálov býva v pamäti a na server
		# sa ide až po žánre, program alebo popisy
		try:
			self.cp.load_channel_list()

			if cat_id == 'radio':
				channels = [ch for ch in self.cp.channels if ch.radio]
			elif cat_id and cat_id != 'all':
				keys = self.cp.get_genre_channel_keys(cat_id)
				channels = [ch for ch in self.cp.channels if ch.key in keys and not ch.radio]
			else:
				channels = [ch for ch in self.cp.channels if not ch.radio]

			self.cp.load_epg(channels)
			self.cp.load_descriptions(channels)
		except SkylinkSessionError:
			self.cp.session_expired()
			return

		enable_adult = self.cp.get_setting('enable_adult')
		enable_download = self.cp.get_setting('download_live')

		for channel in channels:
			if not enable_adult and channel.adult:
				continue

			if channel.epg_name:
				epg_str = '  ' + _I(channel.epg_name)
				info_labels = {
					'plot': '%s - %s\n%s' % (self.cp.timestamp_to_str(channel.epg_start),
					                         self.cp.timestamp_to_str(channel.epg_stop),
					                         channel.epg_desc or ''),
					'title': channel.epg_name,
					'adult': channel.adult,
				}
				if channel.epg_start and channel.epg_stop:
					info_labels['duration'] = channel.epg_stop - channel.epg_start
			else:
				epg_str = ''
				info_labels = {'title': channel.name, 'adult': channel.adult}

			title = channel.name
			if channel.lcn:
				title = '%d. %s' % (channel.lcn, title)

			menu = self.cp.create_ctx_menu()
			if channel.archive and self.cp.archive_module:
				menu.add_menu_item(self.cp._("Archive"),
				                   cmd=self.cp.archive_module.get_archive_days_for_channels,
				                   channel_id=channel.key, archive_hours=channel.archive)

			# náhľad práve bežiacej relácie, picon ako záloha
			img = channel.epg_img or channel.picon

			self.cp.add_video(title + epg_str, img, info_labels, menu=menu,
			                  download=enable_download, cmd=self.cp.get_live_stream,
			                  channel_key=channel.key, channel_name=channel.name)


# ##################################################################################################################

class SkylinkModuleArchive(CPModuleArchive):

	def __init__(self, content_provider):
		CPModuleArchive.__init__(self, content_provider)

	def get_archive_channels(self):
		try:
			self.cp.load_channel_list()
		except SkylinkSessionError:
			self.cp.session_expired()
			return

		enable_adult = self.cp.get_setting('enable_adult')

		for channel in self.cp.channels:
			if not enable_adult and channel.adult:
				continue
			if channel.radio:
				# rádiá sú mimo aj v ostatných zoznamoch
				continue
			if channel.archive > 0:
				self.add_archive_channel(channel.name, channel.key, channel.archive,
				                         img=channel.picon, info_labels={'adult': channel.adult})

	def get_archive_program(self, channel_id, archive_day):
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		# framework počíta rozsah dňa v lokálnom čase, takže v deň zmeny času vyjde
		# 23 alebo 25 hodín - server rozsah dlhší než deň neprijme
		if ts_to - ts_from > ARCHIVE_WINDOW:
			ts_to = ts_from + ARCHIVE_WINDOW

		channel = self.cp.channels_by_key.get(channel_id)
		channel_name = channel.name if channel else ''
		replay_delay = channel.replay_delay if channel else 0

		try:
			events = self.cp.api.get_schedule(channel_id, ts_from, ts_to)
		except SkylinkSessionError:
			self.cp.session_expired()
			return
		except Exception as e:
			self.cp.show_error(self.cp._("Failed to load the TV guide: %s") % error_text(e))
			return

		now = int(time())

		descriptions = {}
		if self.cp.get_setting('load_descriptions'):
			try:
				descriptions = self.cp.api.get_descriptions(
					[e.get('id') for e in events[:DESCRIPTION_LIMIT] if e.get('id')])
			except SkylinkSessionError:
				self.cp.session_expired()
				return
			except Exception as e:
				self.cp.log_error('Failed to load descriptions: %s' % error_text(e))

		for event in events:
			params = event.get('params') or {}
			start = to_timestamp(params.get('start'))
			stop = to_timestamp(params.get('end'))
			name = event.get('title') or ''

			title = '%s - %s - %s' % (self.cp.timestamp_to_str(start),
			                          self.cp.timestamp_to_str(stop), _I(name))

			plot = event.get('desc') or descriptions.get(event.get('id'))
			if not plot:
				plot = event_description(event)

			info_labels = {
				'plot': plot,
				'title': name,
			}
			if start and stop:
				info_labels['duration'] = stop - start
			if start:
				info_labels['year'] = int(strftime('%Y', localtime(start)))
			if params.get('age'):
				info_labels['age'] = params['age']

			img = asset_image(event, 'la', PREVIEW_WIDTH, PREVIEW_HEIGHT)

			if stop > (now - replay_delay) or not (params.get('replay') or params.get('restart')):
				# ešte beží, nevysielalo sa, alebo ho server ešte neuvoľnil do archívu
				self.cp.add_video(_C('grey', title), img, info_labels, download=False, cmd=self.cp.noop)
				continue

			self.cp.add_video(title, img, info_labels, cmd=self.get_archive_stream,
			                  event_id=event.get('id'),
			                  archive_title='%s - %s' % (channel_name, name))

	def get_archive_stream(self, event_id, archive_title):
		return self.cp.play_asset(event_id, archive_title, live=False)

	def get_archive_hours(self, channel_id):
		try:
			self.cp.load_channel_list()
		except Exception:
			return None
		channel = self.cp.channels_by_key.get(channel_id)
		return channel.archive if channel else None

	def get_channel_id_from_path(self, path):
		if path.startswith(('playlive/', 'playlivets/')):
			path = path.split('/', 1)[1]
			if path.endswith('/index.mpd'):
				path = path[:-10]
			elif path.endswith('/index'):
				path = path[:-6]
			try:
				channel_key = base64.b64decode(path.encode('utf-8')).decode('utf-8')
			except Exception:
				return None

			try:
				self.cp.load_channel_list()
			except Exception:
				return None

			channel = self.cp.channels_by_key.get(channel_key)
			return channel_key if channel and channel.archive else None

		return None

	def get_channel_id_from_sref(self, sref):
		try:
			self.cp.load_channel_list()
		except Exception:
			return None

		name = channel_name_normalise(sref.getServiceName())
		channel = self.cp.channels_by_norm_name.get(name)
		return channel.key if channel and channel.archive else None

	def get_archive_event(self, channel_id, event_start, event_end=None):
		try:
			events = self.cp.api.get_schedule(channel_id, event_start - 14400,
			                                  (event_end or event_start) + 14400)
		except SkylinkSessionError:
			self.cp.session_expired()
			return
		except Exception as e:
			self.cp.log_error('Failed to load the archive event: %s' % error_text(e))
			return

		channel = self.cp.channels_by_key.get(channel_id)
		channel_name = channel.name if channel else ''

		for event in events:
			params = event.get('params') or {}
			start = to_timestamp(params.get('start'))
			if abs(start - event_start) > 60:
				continue

			stop = to_timestamp(params.get('end'))
			name = event.get('title') or ''
			title = '%s - %s - %s' % (self.cp.timestamp_to_str(start),
			                          self.cp.timestamp_to_str(stop), _I(name))

			info_labels = {'plot': event_description(event), 'title': name}
			if start and stop:
				info_labels['duration'] = stop - start

			self.cp.add_video(title, asset_image(event, 'la', PREVIEW_WIDTH, PREVIEW_HEIGHT), info_labels,
			                  cmd=self.get_archive_stream, event_id=event.get('id'),
			                  archive_title='%s - %s' % (channel_name, name))
			break


# ##################################################################################################################

class SkylinkModuleExtra(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("Special section"))

	def add(self):
		if self.cp.get_setting('enable_extra'):
			CPModuleTemplate.add(self)

	def root(self, section=None):
		info_labels = {'plot': self._("Here you can see the devices registered to your account and free up a slot.")}
		self.cp.add_dir(self._('Registered devices'), info_labels=info_labels, cmd=self.list_devices)

		info_labels = {'plot': self._("Shows which account the addon is signed in with.")}
		self.cp.add_dir(self._('Account'), info_labels=info_labels, cmd=self.list_account)

		info_labels = {'plot': self._("With this button you can check if playback works OK or it gives some error from the server.")}
		self.cp.add_dir(self._('Check playback'), info_labels=info_labels, cmd=self.check_playback)

		self.cp.add_video(self._("Run EPG export to enigma or XML files"), cmd=self.export_epg)

	def export_epg(self):
		self.cp.bxeg.refresh_xmlepg_start(True)
		self.cp.show_info(self._("EPG export started"), noexit=True)

	def check_playback(self):
		try:
			self.cp.load_channel_list()
		except Exception as e:
			self.cp.show_error(self._("Playback failed: %s") % error_text(e))
			return

		if not self.cp.channels:
			self.cp.show_error(self._("Can't check playback. There are no channels available."))
			return

		channel = self.cp.channels[0]
		try:
			stream = self.cp.api.get_stream(channel.key)
		except Exception as e:
			self.cp.show_error(self._("Playback failed: %s") % error_text(e))
			return

		if stream.get('url') and stream.get('license_url'):
			self.cp.show_info(self._("No error occured during playback check. Playback should work."))
		else:
			self.cp.show_error(self._("The server did not return a stream or a license address."))

	def list_account(self):
		info = self.cp.api.user_info or {}

		name = info.get('user') or ''
		if name:
			self.cp.add_video(self._("Signed in as: %s") % name, None, {}, download=False, cmd=self.cp.noop)

		service = info.get('community') or BRANDS.get(self.cp.api.brand, {}).get('title', '')
		if service:
			self.cp.add_video(self._("Service: %s") % service, None, {}, download=False, cmd=self.cp.noop)

		self.cp.add_video(self._("Device: %s") % (self.cp.get_setting('device_serial') or '?'),
		                  None, {}, download=False, cmd=self.cp.noop)

		self.cp.add_dir(_I(self._("Sign out this device")), cmd=self.cp.sign_out)

	def list_devices(self):
		try:
			devices = self.cp.api.get_devices()
		except SkylinkSessionError:
			self.cp.session_expired()
			return
		except Exception as e:
			self.cp.show_error(self._("Failed to load the device list: %s") % error_text(e))
			return

		own_serial = self.cp.get_setting('device_serial')

		for device in devices:
			name = (device.get('devicePrettyName') or device.get('deviceModel')
			        or device.get('name') or device.get('deviceSerial') or '?')
			serial = device.get('deviceSerial') or device.get('id') or ''

			title = name
			menu = self.cp.create_ctx_menu()

			if serial and serial == own_serial:
				title += ' *'
				info_labels = {'plot': self._("This is the device used by the addon.")}
			else:
				info_labels = {'plot': self._("In the menu you can remove this device and free up a slot.")}
				if serial:
					menu.add_menu_item(self._('Remove device!'), cmd=self.remove_device,
					                   device_name=name, device_serial=serial)

			self.cp.add_video(title, None, info_labels, menu=menu, download=False, cmd=self.cp.noop)

	def remove_device(self, device_name, device_serial):
		if not self.cp.get_yes_no_input(self._("Do you really want to remove the device %s?") % device_name):
			return

		try:
			self.cp.api.create_session(remove_device=device_serial)
		except Exception as e:
			self.cp.show_error(self._("Failed to remove the device: %s") % error_text(e))
			return

		self.cp.show_info(self._("Device %s was removed.") % device_name, noexit=True)
		self.cp.refresh_screen()


# ##################################################################################################################

class SkylinkContentProvider(ModuleContentProvider):

	def __init__(self):
		ModuleContentProvider.__init__(self)

		# nech je v logu vidno, ktorá verzia doplnku práve beží
		self.log_info('Skylink Live TV %s (build %d)' % (ADDON_VERSION, ADDON_BUILD))

		# pri zmene týchto nastavení sa prihlási znova
		self.login_settings_names = ('brand', 'username', 'password')

		self.api = SkylinkApi(self)
		self.channels = []
		self.channels_by_key = {}
		self.channels_by_norm_name = {}
		self.channels_next_load_time = 0
		self.genre_cache = {}
		self.checksum = None

		self.drm_failed = False

		self.bxeg = SkylinkBouquetXmlEpgGenerator(self)

		self.archive_module = SkylinkModuleArchive(self)

		self.modules = [
			SkylinkModuleLiveTV(self),
			self.archive_module,
			SkylinkModuleExtra(self),
		]

	# ##############################################################################################################
	# prihlásenie

	def login(self, silent):
		brand = self.get_setting('brand') or 'slsk'
		username = (self.get_setting('username') or '').strip()
		password = self.get_setting('password') or ''

		if not username or not password:
			return False

		device_serial = (self.get_setting('device_serial') or '').strip()
		if not self.api.valid_device_serial(device_serial):
			device_serial = self.api.new_device_serial()
			self.set_setting('device_serial', device_serial)
			# session patrí k starému zariadeniu, zahoď ju
			self.set_setting('session', '')

		saved_sso = (self.get_setting('session') or '').strip()
		self.api.setup(brand, device_serial, saved_sso)

		self.channels = []
		self.channels_by_key = {}
		self.channels_by_norm_name = {}
		self.channels_next_load_time = 0
		self.genre_cache = {}
		# po zmene značky nesmie zostať visieť kontrolný súčet starej ponuky
		self.checksum = None

		# 1. skús uloženú session
		if saved_sso:
			try:
				self.api.create_session()
				return True
			except Exception as e:
				self.log_info('Saved session is no longer valid: %s' % error_text(e))
				self.api.sso_token = None
				self.set_setting('session', '')

		# 2. prihlásenie menom a heslom
		try:
			sso = self.api.login(username, password)
			self.save_session(sso)
			self.api.create_session()
		except Exception as e:
			msg = error_text(e)
			self.log_error('Skylink login error: %s' % msg)
			self.login_error(self.translate_error(msg))
			return False

		return True

	def translate_error(self, msg):
		"""Hlášky platformy sú kľúče typu sg.ui.sso.error.* - preložíme tie bežné."""
		low = (msg or '').lower()
		if 'credential' in low or 'password' in low or 'invalid_login' in low or 'wrong' in low:
			return self._("Wrong username or password - check the addon settings.")
		if 'device' in low or 'max_session' in low or 'toomany' in low or 'too_many' in low:
			return self._("The limit of registered devices has been reached. Remove one device in the Special section, in the Skylink app or on the website.")
		if 'block' in low or 'suspend' in low:
			return self._("The account is blocked or inactive.")
		return self._("Sign-in failed: %s") % msg

	def save_session(self, sso_token):
		"""Uloží prihlasovací token - volá sa aj pri jeho výmene zo strany servera."""
		self.set_setting('session', sso_token or '')

	def forget_session(self):
		self.set_setting('session', '')
		self.api.sso_token = None
		self.api.token = None

	def session_expired(self):
		"""Zahodí prihlásenie a nechá framework prihlásiť znova.

		Musí to byť cez login_error - tá vyhodí výnimku, ktorú engine zachytí,
		prihlási sa nanovo a zopakuje rozbehnutú akciu. Obyčajná hláška by
		doplnok nechala v stave, keď sa o nové prihlásenie nikto nepokúsi.
		"""
		self.forget_session()
		self.login_error(self._("Your sign-in has expired."))

	def sign_out(self):
		if not self.get_yes_no_input(self._("Do you really want to sign out? The saved sign-in will be deleted, the username and password stay in the settings.")):
			return

		self.forget_session()
		self.login_error(self._("Signed out."))

	def noop(self):
		return

	def logged_in(self):
		return self.api.logged_in()

	# ##############################################################################################################
	# kanály

	def timestamp_to_str(self, timestamp, format_str='%H:%M'):
		if not timestamp:
			return ''
		return strftime(format_str, localtime(timestamp))

	def load_channel_list(self, force=False):
		"""Načíta zoznam kanálov - najviac raz za CHANNELS_CACHE_SECONDS."""
		if not force and self.channels and int(time()) < self.channels_next_load_time:
			return

		entries = self.api.get_channels(force=force)

		if not entries:
			if not self.channels:
				# bez kanálov by generátor prepísal userbouquet na prázdny a export
				# programu by sa uložil ako úspešný bez jedinej relácie
				self.log_error('Empty channel list received and no previous list is available')
				raise Exception(self._("The server returned an empty channel list."))

			# server nič nevrátil - radšej nechaj starý zoznam, inak by sa vyprázdnil userbouquet
			self.log_error('Empty channel list received - keeping the previous one')
			self.channels_next_load_time = int(time()) + 60
			return

		channels = []
		used_ids = set()

		for entry in entries:
			key = asset_channel_id(entry)
			if not key:
				continue

			params = entry.get('params') or {}
			name = channel_title(entry) or str(key)

			archive = 0
			if params.get('replay') or params.get('restart'):
				archive = 168
				expiry = params.get('replayExpiry')
				if expiry:
					try:
						archive = int(expiry) // 3600
					except (TypeError, ValueError):
						pass

			try:
				replay_delay = int(params.get('replayDelay') or 0)
			except (TypeError, ValueError):
				replay_delay = 0

			channel = SkylinkChannel(
				key=key,
				cid=self.channel_numeric_id(key, used_ids),
				name=name,
				picon=asset_image(entry, 'la'),
				# kanály pre dospelých sú na tejto platforme značené ako chránené PIN-om
				adult=bool(params.get('adult') or params.get('pinProtected')),
				archive=archive,
				lcn=params.get('lcn') if isinstance(params.get('lcn'), int) else None,
			)
			channel.radio = bool(params.get('radio'))
			channel.replay_delay = replay_delay

			# niektoré odpovede nesú bežiaci program rovno pri kanáli
			now_event = params.get('now')
			if isinstance(now_event, dict) and now_event.get('title'):
				self.set_channel_epg(channel, now_event)

			channels.append(channel)

		# zoznam priraď až nakoniec, aby iné vlákno nevidelo nový zoznam
		# so starými registrami
		by_key = dict((ch.key, ch) for ch in channels)
		by_norm_name = dict((channel_name_normalise(ch.name), ch) for ch in channels)

		self.channels_by_key = by_key
		self.channels_by_norm_name = by_norm_name
		self.channels = channels
		self.channels_next_load_time = int(time()) + CHANNELS_CACHE_SECONDS
		self.genre_cache = {}

		# zostavenie je súčasťou súčtu zámerne - ak sa zmení výpočet číselných id,
		# musí sa prepísať aj userbouquet, inak by mal iné service id než EPG
		source = 'build=%d|%s' % (ADDON_BUILD,
		                          '|'.join('%s=%s' % (ch.key, ch.name) for ch in channels))
		self.checksum = md5(source.encode('utf-8')).hexdigest()

		self.log_debug('Loaded %d channels' % len(channels))

	@staticmethod
	def set_channel_epg(channel, event):
		"""Prenesie reláciu na kanál - názov, čas, obrázok a popis."""
		params = event.get('params') or {}

		channel.epg_id = event.get('id')
		channel.epg_name = event.get('title')
		channel.epg_start = to_timestamp(params.get('start'))
		channel.epg_stop = to_timestamp(params.get('end'))
		channel.epg_img = asset_image(event, 'la', PREVIEW_WIDTH, PREVIEW_HEIGHT)

		desc = event.get('desc')
		if desc:
			channel.epg_desc = desc
			channel.epg_full_desc = True
		else:
			channel.epg_desc = event_description(event)
			channel.epg_full_desc = False

	@staticmethod
	def channel_numeric_id(key, used_ids):
		"""Stabilné číselné id kanála pre bouquet a EPG.

		Pri kolízii sa počíta znova z kľúča s príponou - poradie kanálov tak
		rozhoduje až pri kolízii, inak je id dané len kľúčom.

		Horná hranica je 0xFFFD, lebo generátor bouquetu počíta service id ako
		(sid_start + id) % 0xFFFF, kým generátory programu bez zvyšku. Pri vyššom
		id by kanál mal v bouquete iné service id než v EPG a zostal by bez programu.
		"""
		for attempt in range(0, 50):
			source = key if attempt == 0 else '%s#%d' % (key, attempt)
			cid = 1 + (crc32(source.encode('utf-8')) & 0xFFFFFFFF) % 0xFFFD
			if cid not in used_ids:
				used_ids.add(cid)
				return cid

		cid = 1
		while cid in used_ids:
			cid += 1
		used_ids.add(cid)
		return cid

	def get_genre_channel_keys(self, query):
		"""Kľúče kanálov v žánrovej skupine."""
		cached = self.genre_cache.get(query)
		if cached is not None:
			return cached

		keys = set()
		next_asset = None

		for page in range(0, 20):
			try:
				assets, next_asset = self.api.get_assets(query, limit=100, next_asset=next_asset)
			except SkylinkSessionError:
				raise
			except Exception as e:
				self.log_error('Genre %s failed: %s' % (query, error_text(e)))
				break

			for asset in assets:
				key = asset_channel_id(unwrap_asset(asset))
				if key:
					keys.add(key)

			if not next_asset or not assets:
				break

		self.genre_cache[query] = keys
		return keys

	def load_epg(self, channels):
		"""Doplní ku kanálom práve bežiaci program. Pýta sa len na tie, ktoré ho nemajú."""
		now = int(time())

		keys = [ch.key for ch in channels
		        if not ch.epg_name or not ch.epg_stop or ch.epg_stop < now][:EPG_MAX_CHANNELS]
		if not keys:
			return

		for start in range(0, len(keys), EPG_BATCH):
			batch = keys[start:start + EPG_BATCH]
			try:
				epg = self.api.get_schedule_now(batch)
			except SkylinkSessionError:
				raise
			except Exception as e:
				self.log_error('Failed to load the EPG: %s' % error_text(e))
				return

			for key, events in epg.items():
				channel = self.channels_by_key.get('%s' % (key,))
				if not channel:
					continue

				if isinstance(events, dict):
					events = [events]
				if not isinstance(events, list) or not events:
					continue

				# odpoveď nesie viac relácií a bežiaca nemusí byť prvá
				event = None
				for candidate in events:
					if not isinstance(candidate, dict):
						continue
					params = candidate.get('params') or {}
					start = to_timestamp(params.get('start'))
					stop = to_timestamp(params.get('end'))
					if start and stop and start <= now < stop:
						event = candidate
						break

				if event is None:
					continue

				self.set_channel_epg(channel, event)


	def load_descriptions(self, channels):
		"""Dotiahne skutočné popisy relácií. API ich pri programe neposiela,
		sú len v detaile položky, čiže je to jedna požiadavka na kanál."""
		if not self.get_setting('load_descriptions'):
			return

		todo = [ch for ch in channels if ch.epg_id and ch.epg_name and not ch.epg_full_desc]
		if not todo:
			return

		todo = todo[:DESCRIPTION_LIMIT]

		try:
			descriptions = self.api.get_descriptions([ch.epg_id for ch in todo])
		except SkylinkSessionError:
			raise
		except Exception as e:
			self.log_error('Failed to load descriptions: %s' % error_text(e))
			return

		for channel in todo:
			desc = descriptions.get(channel.epg_id)
			if desc:
				channel.epg_desc = desc
				channel.epg_full_desc = True

	def get_channel_epg(self, channel_key, time_from, time_to):
		"""Program kanála pre bouquet a XML EPG."""
		return self.api.get_schedule(channel_key, time_from, time_to)

	# ##############################################################################################################
	# prehrávanie

	def stream_headers(self, web=None):
		"""Hlavičky, s ktorými si manifest a segmenty pýta ich webový prehrávač."""
		web = web or self.api.web_url()
		return {
			'Origin': web,
			'Referer': web + '/',
			'User-Agent': USER_AGENT,
		}

	def get_dash_info(self, stream_key):
		"""Údaje pre DashHTTPRequestHandler - manifest a licenčná konfigurácia."""
		web = stream_key.get('web') or self.api.web_url()

		license_headers = self.stream_headers(web)
		license_headers['Content-Type'] = 'application/octet-stream'

		info = {
			'ext_drm_decrypt': self.get_setting('ext_drm_decrypt'),
			'url': stream_key['url'],
			'bandwidth': stream_key.get('bandwidth'),
			'headers': self.stream_headers(web),
		}

		# licenčná adresa patrí systému, ktorý vybral server
		if str(stream_key.get('drm_system', '')).lower().startswith('play'):
			license_headers['Content-Type'] = 'text/xml; charset=utf-8'
			info['drm'] = {
				'pr': {
					'license_url': stream_key.get('license_url', ''),
					'headers': license_headers,
				}
			}
		else:
			info['drm'] = {
				'wv': {
					'license_url': stream_key.get('license_url', ''),
					'privacy_mode': bool(stream_key.get('privacy_mode')),
					'headers': license_headers,
				}
			}

		return info

	def playready_wanted(self):
		return not is_py2 and not self.drm_failed and self.get_setting('drm_playready')

	def get_stream_info(self, asset_id):
		"""Vráti adresu manifestu a licencie - používa aj HTTP handler pre bouquet."""
		stream = self.api.get_stream(asset_id, playready=self.playready_wanted())

		mpd_url = stream.get('url') or ''
		if mpd_url:
			# len server - v adrese je prístupový token
			self.log_info('Stream from: %s' % (mpd_url.split('/')[2] if mpd_url.count('/') >= 2 else '?'))

		return stream

	def get_live_stream(self, channel_key, channel_name=''):
		return self.play_asset(channel_key, channel_name, live=True)

	def play_asset(self, asset_id, stream_title='', live=False):
		if not asset_id:
			self.show_error(self._("Missing item identifier."))
			return

		if self.get_setting('drm_playready'):
			if is_py2:
				self.show_info(self._("You have enabled 1080p streams in addon settings. This option works only in distributions based on python 3.8+ like OpenATV 7.x, OpenPLi > 9.x etc. Update software in you receiver to get better quality streams."), noexit=True)
			elif self.drm_failed:
				self.show_info(self._("Playback of stream with 1080p quality failed. Switching back to 720p quality."), noexit=True)

		try:
			stream = self.get_stream_info(asset_id)
		except SkylinkSessionError:
			self.session_expired()
			return
		except Exception as e:
			msg = error_text(e)
			self.log_error('Skylink stream error: %s' % msg)
			low = msg.lower()
			if 'entitle' in low or 'subscri' in low or 'not_allowed' in low or 'noaccess' in low:
				self.show_error(self._("This channel is not part of your subscription."))
			elif 'geo' in low:
				self.show_error(self._("The broadcast is not available from this network (geoblocking)."))
			else:
				self.show_error(self._("Playback failed: %s") % msg)
			return

		mpd_url = stream.get('url') or ''
		license_url = stream.get('license_url') or ''

		if not mpd_url:
			self.show_error(self._("No stream URL received from server."))
			return

		if not license_url:
			self.show_error(self._("No license URL received. The stream cannot be played."))
			return

		if not self.resolve_dash_streams(mpd_url, license_url, stream_title or stream.get('title') or '', live,
		                                 stream.get('drm_system') or ''):
			self.show_error(self._("Failed to load the DASH stream."))

	def limit_streams(self, streams):
		"""Odfiltruje streamy nad nastavené rozlíšenie. Keď by neostalo nič,
		necháva ten najmenší, aby sa dalo prehrať aspoň niečo."""
		try:
			max_height = int(self.get_setting('max_resolution') or 0)
		except Exception:
			max_height = 0

		if not max_height or not streams:
			return streams

		allowed = []
		for s in streams:
			try:
				height = int(s.get('height') or 0)
			except Exception:
				height = 0
			# stream bez uvedeného rozlíšenia je u nich ten najvyšší (1920x1080
			# je uvedené až na nadradenej skupine), pri nastavenom strope ho vynechaj
			if height and height <= max_height:
				allowed.append(s)

		if not allowed:
			# žiadny nevyhovuje, vezmi najnižší dostupný
			allowed = [min(streams, key=lambda x: int(x.get('height') or 0) or 99999)]

		return allowed

	def resolve_streams_for_channel(self, manifest_url):
		"""Streamy manifestu podľa nastavení - používa aj HTTP handler pre bouquet."""
		streams = self.get_dash_streams(manifest_url, headers=self.stream_headers(),
		                                max_bitrate=self.get_setting('max_bitrate'))

		if streams:
			# do logu, nech je vidieť, čo kanál vôbec ponúka
			self.log_debug('Streams offered by the channel: %s' % ', '.join(
				'%sp/%s' % (s.get('height') or '?', s.get('bandwidth') or '?') for s in streams))

		return self.limit_streams(streams)

	def resolve_dash_streams(self, manifest_url, license_url, title, live, drm_system=''):
		streams = self.resolve_streams_for_channel(manifest_url)
		if not streams:
			return False

		privacy_mode = self.get_setting('privacy_mode')
		web = self.api.web_url()

		for s in streams:
			stream_key = {
				'url': s['playlist_url'],
				'bandwidth': s['bandwidth'],
				'license_url': license_url,
				'drm_system': drm_system,
				'privacy_mode': privacy_mode,
				'web': web,
			}
			url = stream_key_to_dash_url(self.http_endpoint, stream_key)

			info_labels = {
				'bandwidth': int(s['bandwidth']),
				# niektoré streamy nemajú v manifeste uvedené rozlíšenie
				'quality': s['height'] + 'p' if s.get('height') else 'max',
			}
			self.add_play(title, url, info_labels=info_labels, live=live)

		return True
