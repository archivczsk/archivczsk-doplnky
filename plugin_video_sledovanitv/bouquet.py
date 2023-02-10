# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, XmlEpgGenerator

NAME_PREFIX = "sledovanitv"
NAME = "SledovaniTV"
SERVICEREF_SID_START = 0x500
SERVICEREF_TID = 0xA0
SERVICEREF_ONID = 12
SERVICEREF_NAMESPACE = 0xAB40000

# #################################################################################################


class SledovaniTVXmlEpgGenerator(XmlEpgGenerator):

	def get_epg(self, channel, fromts, tots):
		if not self.epg_data:
			# api allows to load only epg for all channels and has limit on how big response can be
			# to overcome this, load epg data splited by 24 hours
			self.epg_data = []
			for i in range((tots - fromts) // 86400):
				f = fromts + (i * 86400)
				self.epg_data.append(self.bxeg.cp.sledovanitv.get_epg(f, f + 86400))

		for epg in self.epg_data:
			for event in epg.get(channel['channel_id'], []):
				if self.bxeg.cp.sledovanitv.epg_event_is_garbage(event):
					continue

				yield {
					'start': self.bxeg.cp.sledovanitv.convert_time(event["startTime"]),
					'end': self.bxeg.cp.sledovanitv.convert_time(event["endTime"]),
					'title': event['title'],
					'desc': event['description']
				}

	def run(self, force):
		# mark, that we don't have loaded epg data yet
		self.epg_data = None
		XmlEpgGenerator.run(self, force)
		# free used memory
		del self.epg_data

# #################################################################################################


class SledovaniTVBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider, http_endpoint, user_agent):
		self.prefix = NAME_PREFIX
		self.name = NAME
		self.sid_start = SERVICEREF_SID_START
		self.tid = SERVICEREF_TID
		self.onid = SERVICEREF_ONID
		self.namespace = SERVICEREF_NAMESPACE
		BouquetXmlEpgGenerator.__init__(self, content_provider, http_endpoint, login_settings_names=('username', 'password', 'pin', 'serialid'), user_agent=user_agent)
		self.xmlepg_generator = SledovaniTVXmlEpgGenerator

	def logged_in(self):
		return self.cp.sledovanitv != None

	def get_channels_checksum(self, channel_type):
		return self.cp.checksum

	def load_channel_list(self):
		self.cp.load_channel_list()

	def get_bouquet_channels(self, channel_type=None):
		i = 0
		for channel in self.cp.channels:
			if channel['type'] == 'tv':
				yield {
					'name': channel['name'],
					'adult': channel['adult'],
					'picon': channel['picon'],
					'id': i,
					'key': str(channel['id']),
				}
				i += 1

	def get_xmlepg_channels(self):
		i = 0
		for channel in self.cp.channels:
			if channel['type'] == 'tv':
				yield {
					'name': channel['name'],
					'id': i,
					'channel_id': channel['id']
				}
				i += 1

# #################################################################################################
