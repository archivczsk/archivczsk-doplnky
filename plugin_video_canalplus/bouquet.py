# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator
from .canalplus_api import event_details


class CanalplusBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider):
		BouquetXmlEpgGenerator.__init__(self, content_provider,
		                                login_settings_names=('brand',))

	def logged_in(self):
		return self.cp.logged_in()

	def get_channels_checksum(self, channel_type):
		return self.cp.checksum

	def load_channel_list(self):
		self.cp.load_channel_list()

	def get_bouquet_channels(self, channel_type=None):
		for channel in self.cp.channels:
			yield {
				'name': channel.name,
				'picon': channel.picon,
				'id': channel.id,
				'key': channel.key,
			}

	def get_xmlepg_channels(self):
		for channel in self.cp.channels:
			yield {
				'name': channel.name,
				'id': channel.id,
				'key': channel.key,
			}

	def get_epg(self, channel, fromts, tots):
		for ev in self.cp.get_channel_epg(channel['key'], int(fromts), int(tots)):
			if not ev.get('start') or not ev.get('end'):
				continue
			yield {
				'start': ev['start'],
				'end': ev['end'],
				'title': ev.get('title') or '',
				'desc': event_details(ev),
			}
