# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, XmlEpgGenerator

NAME_PREFIX = "rebittv"
NAME = "RebitTV"

SERVICEREF_SID_START = 0x700
SERVICEREF_TID = 0xF1
SERVICEREF_ONID = 11
SERVICEREF_NAMESPACE = 0xAA10000

# #################################################################################################


class RebitTVXmlEpgGenerator(XmlEpgGenerator):

	def get_epg(self, channel, fromts, tots):
		fromts2 = self.epg_current.get(channel['id'], {}).get('start', fromts - 7200) - 1

		for event in self.bxeg.cp.rebittv.get_epg(channel['key'], fromts2, tots):
			yield {
				'start': event['start'],
				'end': event['stop'],
				'title': event['title'],
				'desc': event['description']
			}

	def run(self, force):
		self.epg_current = self.bxeg.cp.rebittv.get_current_epg()
		XmlEpgGenerator.run(self, force)
		del self.epg_current


class RebitTVBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider, http_endpoint, user_agent):
		self.prefix = NAME_PREFIX
		self.name = NAME
		self.sid_start = SERVICEREF_SID_START
		self.tid = SERVICEREF_TID
		self.onid = SERVICEREF_ONID
		self.namespace = SERVICEREF_NAMESPACE
		BouquetXmlEpgGenerator.__init__(self, content_provider, http_endpoint, login_settings_names=('username', 'password', 'device_name'), user_agent=user_agent)
		self.xmlepg_generator = RebitTVXmlEpgGenerator

	def logged_in(self):
		return self.cp.rebittv != None

	def get_channels_checksum(self, channel_type):
		return self.cp.checksum

	def load_channel_list(self):
		self.cp.load_channel_list()

	def get_bouquet_channels(self, channel_type=None):
		for channel in self.cp.channels:
			yield {
				'name': channel['name'],
				'adult': channel['adult'],
				'picon': channel['picon'],
				'id': int(channel['number']),
				'key': str(channel['id']),
			}

	def get_xmlepg_channels(self):
		for channel in self.cp.channels:
			if channel['has_epg']:
				yield {
					'name': channel['name'],
					'id': int(channel['number']),
					'id_content': channel['slug'],
					'key': str(channel['id']),
				}

# #################################################################################################
