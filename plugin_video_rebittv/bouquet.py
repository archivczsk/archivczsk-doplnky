# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, XmlEpgGenerator, EnigmaEpgGenerator

# #################################################################################################

class RebitTVEpgGenerator(object):

	def get_epg(self, channel, fromts, tots):
		fromts2 = self.epg_current.get(channel['id'], {}).get('start', fromts - 7200) - 1

		for event in self.bxeg.cp.rebittv.get_epg(channel['key'], fromts2, tots):
			yield {
				'start': event['start'],
				'end': event['stop'],
				'title': event['title'],
				'desc': event['description']
			}

class RebitTVXmlEpgGenerator(RebitTVEpgGenerator, XmlEpgGenerator):
	def run(self, force):
		self.epg_current = self.bxeg.cp.rebittv.get_current_epg()
		XmlEpgGenerator.run(self, force)
		del self.epg_current

class RebitTVEnigmaEpgGenerator(RebitTVEpgGenerator, EnigmaEpgGenerator):
	def run(self, force):
		self.epg_current = self.bxeg.cp.rebittv.get_current_epg()
		EnigmaEpgGenerator.run(self, force)
		del self.epg_current


class RebitTVBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider):
		BouquetXmlEpgGenerator.__init__(self, content_provider, login_settings_names=('username', 'password', 'device_name'))
		self.xmlepg_generator = RebitTVXmlEpgGenerator
		self.enigmaepg_generator = RebitTVEnigmaEpgGenerator

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
