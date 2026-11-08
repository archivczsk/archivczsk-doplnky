# -*- coding: utf-8 -*-
#
# Userbouquet and XML EPG generator for Skylink.
# Runs in the background and is triggered by a change of settings or the channel list.

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator

import time

from .skylink_api import (to_timestamp, event_description, error_text, EPG_ALIGN, ADDON_BUILD,
                          SkylinkSessionError)

# the server gives the schedule per day, it is requested in daily windows
EPG_WINDOW = 24 * 3600

# this many channels in a row may fail before the export is given up - one removed channel
# must not bring down the whole run, but an error common to all channels must be propagated
EPG_MAX_FAILURES = 5

# #################################################################################################


class SkylinkBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider):
		# only_subscribed changes the channel list like another account - the userbouquet and EPG are rebuilt after a change
		BouquetXmlEpgGenerator.__init__(self, content_provider,
		                                login_settings_names=('brand', 'username', 'password', 'only_subscribed'))
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
		"""The framework remembers the time of every successful export and doesn't attempt a new
		one for 20 hours. After an addon update that memory is reset, so the new export
		doesn't have to wait for those 20 hours to pass."""
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
				# radios don't belong to the TV bouquet
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
		"""Channel schedule for the whole requested range.

		The server returns the schedule per day, so the range is split into daily windows.
		Their own client does the same. The boundaries are aligned to quarter hours already
		here, so that every window is exactly one day - the server doesn't accept a longer range.
		"""
		# with hundreds of channels don't flood the server
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

				# An expired login or an error repeated on several channels in a row must be
				# propagated - otherwise the framework would store the export as successful
				# without a single programme and wouldn't attempt a new one for 20 hours.
				# One removed channel (the server answers 404 for it) on the other hand must not
				# bring down the whole export, because it would then never finish.
				if isinstance(e, SkylinkSessionError) or self.epg_failures >= EPG_MAX_FAILURES:
					raise

				return

			for event in events:
				params = event.get('params') or {}

				start = to_timestamp(params.get('start'))
				end = to_timestamp(params.get('end'))
				if not start or not end:
					continue

				# the windows may overlap, send the same programme once
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
