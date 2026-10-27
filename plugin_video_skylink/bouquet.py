# -*- coding: utf-8 -*-
#
# Generátor userbouquetu a XML EPG pre Skylink.
# Beží na pozadí a spúšťa sa pri zmene nastavení alebo zoznamu kanálov.

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator

import time

from .skylink_api import (to_timestamp, event_description, error_text, EPG_ALIGN, ADDON_BUILD,
                          SkylinkSessionError)

# server dáva program po dňoch, pýtame si ho v denných oknách
EPG_WINDOW = 24 * 3600

# toľko kanálov po sebe smie zlyhať, kým export vzdáme - jeden zrušený kanál
# nemá zhodiť celý beh, ale chybu spoločnú pre všetky kanály treba prepustiť
EPG_MAX_FAILURES = 5

# #################################################################################################


class SkylinkBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider):
		BouquetXmlEpgGenerator.__init__(self, content_provider,
		                                login_settings_names=('brand', 'username', 'password'))
		self.epg_failures = 0

	# #################################################################################################

	def logged_in(self):
		return self.cp.logged_in()

	def get_channels_checksum(self, channel_type):
		return self.cp.checksum

	def load_channel_list(self):
		self.cp.load_channel_list()

	# #################################################################################################

	def refresh_xmlepg(self, force=False):
		"""Framework si po každom úspešnom exporte zapamätá čas a 20 hodín sa o nový
		nepokúsi. Po aktualizácii doplnku si tú pamäť vynulujeme, aby nový export
		nemusel čakať na uplynutie tých 20 hodín."""
		try:
			state = self.cp.load_cached_data('skylink')
			if state.get('epg_build') != ADDON_BUILD:
				cached = self.cp.load_cached_data('enigmaepg')
				if cached.get('last_export'):
					cached['last_export'] = 0
					self.cp.save_cached_data('enigmaepg', cached)
				state['epg_build'] = ADDON_BUILD
				self.cp.save_cached_data('skylink', state)
				self.cp.log_info('New addon build - the stored EPG export time was dropped')
		except Exception:
			self.cp.log_exception()

		self.epg_failures = 0
		return BouquetXmlEpgGenerator.refresh_xmlepg(self, force)

	# #################################################################################################

	def get_bouquet_channels(self, channel_type=None):
		for channel in self.cp.channels:
			if channel.radio:
				# rádiá do TV bouquetu nepatria
				continue
			yield {
				'name': channel.name,
				'adult': channel.adult,
				'picon': channel.picon,
				'id': channel.id,
				'key': channel.key,
			}

	def get_xmlepg_channels(self):
		for channel in self.cp.channels:
			if channel.radio:
				continue
			yield {
				'name': channel.name,
				'id': channel.id,
				'key': channel.key,
			}

	# #################################################################################################

	def get_epg(self, channel, fromts, tots):
		"""Program kanála pre celý vyžiadaný rozsah.

		Server vracia program po dňoch, preto si rozsah rozdelíme na denné okná.
		Ich vlastný klient to robí rovnako. Hranice zarovnáme na štvrťhodiny už tu,
		aby každé okno vyšlo presne na jeden deň - server dlhší rozsah neprijme.
		"""
		# pri stovkách kanálov nech sa server nezahltí
		time.sleep(0.2)

		seen = set()
		window_from = (int(fromts) // EPG_ALIGN) * EPG_ALIGN
		tots = (int(tots) // EPG_ALIGN) * EPG_ALIGN
		if tots <= window_from:
			tots = window_from + EPG_ALIGN

		while window_from < tots:
			window_to = min(window_from + EPG_WINDOW, tots)

			try:
				events = self.cp.get_channel_epg(channel['key'], window_from, window_to)
				self.epg_failures = 0
			except Exception as e:
				self.epg_failures += 1
				self.cp.log_error('EPG for %s failed: %s' % (channel['name'], error_text(e)))

				# Vypršané prihlásenie alebo chyba opakovaná na viacerých kanáloch
				# po sebe sa musí prepustiť ďalej - inak by framework uložil export
				# ako úspešný bez jedinej relácie a 20 hodín by sa o nový nepokúsil.
				# Jeden zrušený kanál (server naň odpovie 404) naopak celý export
				# zhodiť nemá, lebo by sa potom nedokončil nikdy.
				if isinstance(e, SkylinkSessionError) or self.epg_failures >= EPG_MAX_FAILURES:
					raise

				return

			for event in events:
				params = event.get('params') or {}

				start = to_timestamp(params.get('start'))
				end = to_timestamp(params.get('end'))
				if not start or not end:
					continue

				# okná sa môžu prekrývať, tú istú reláciu pošli raz
				key = event.get('id') or '%s-%s' % (start, end)
				if key in seen:
					continue
				seen.add(key)

				yield {
					'start': start,
					'end': end,
					'title': event.get('title') or '',
					'desc': event_description(event),
				}

			window_from = window_to
