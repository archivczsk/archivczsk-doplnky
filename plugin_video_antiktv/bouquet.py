# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator
from datetime import datetime
import itertools

NAME_PREFIX = "antiktv"
NAME = "AntikTV"
SERVICEREF_SID_START = 0x0000
SERVICEREF_TID = 0
SERVICEREF_ONID = 0
SERVICEREF_NAMESPACE = 0xE010000

# #################################################################################################

class AntikTVBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider, http_endpoint):
		self.prefix = NAME_PREFIX
		self.name = NAME
		self.sid_start = SERVICEREF_SID_START
		self.tid = SERVICEREF_TID
		self.onid = SERVICEREF_ONID
		self.namespace = SERVICEREF_NAMESPACE
		BouquetXmlEpgGenerator.__init__(self, content_provider, http_endpoint, login_settings_names=('username', 'password'), channel_types=('tv', 'radio', 'cam'))

	def logged_in(self):
		return self.cp.atk.is_logged()

	def get_channels_checksum(self, channel_type):
		return self.cp.atk.get_channels_checksum(channel_type)

	def load_channel_list(self):
		self.cp.atk.update_channels()

	def get_bouquet_channels(self, channel_type=None):
		'''
		Tou need to implement this to get list of channels included bouquet for specified channel_type (if used)
		Each channel is a map with these requiered fields:
		{
			'name': "channel name",
			'id': 'unique numeric id of channel the same as in function get_xmlepg_channels()'
			'key': key used to get stream address - it will be encoded and forwarded to http handler
			'adult': indicates if channel is for adults
			'picon': url with picon for this channel
			'is_separator': if true, then this item indicates separator in bouquets
		}
		'''

		for cat in self.cp.atk.get_categories(channel_type):
			if channel_type == 'tv':
				yield {
					'name': cat['name'],
					'adult': cat['name'].startswith(u'Erotic'),
					'is_separator': True
				}

			for channel in self.cp.atk.get_channels(channel_type, cat['id']):
				yield {
					'name': channel['name'],
					'adult': channel['adult'],
					'picon': (channel['logo'].replace('.png', '_100x100.png'), channel['logo']),
					'id': channel['id'],
					'key': '%s:%d' % (channel_type, channel['id']),
				}

	def get_xmlepg_channels(self):
		'''
		Tou need to implement this to get list of channels included in XML-EPG file
		Each channel is a map with these requiered fields:
		{
			'name': "channel name",
			'id': 'unique numeric id of channel - the same as in get_bouquet_channels'
			'id_content': 'unique string representation of channel - only letters, numbers and _ are allowed.' # optional - if not provided, it will be generated from name
		}
		'''

		for channel_type in ('tv', 'radio'):
			for channel in self.cp.atk.get_channels(channel_type):
				yield {
					'name': channel['name'],
					'id': channel['id'],
					'id_content': channel['id_content'],
				}

	def get_epg(self, channel, fromts, tots):
		'''
		You need to implement this to get list of epg events for channel and time range
		Each epg event is a map with these fields:
		{
			'start': timestamp of event start
			'end': timestamp of event end
			'title': 'event title as string'
			'desc': 'description of event as string'
		}
		'''

		def ts_convert(ts):
			return datetime.fromtimestamp(ts).strftime('%Y%m%dT%H%M%S') + '+0000'

		for event in self.cp.atk.get_channel_epg(channel['id_content'], ts_convert(fromts - 7200), ts_convert(tots)):
			yield {
				'start': event['start_timestamp'],
				'end': event['stop_timestamp'],
				'title': event['title'],
				'desc': event.get('description')
			}

