# -*- coding: utf-8 -*-

import os, traceback
try:
	import cPickle as pickle
except:
	import pickle

from time import time
from datetime import datetime
from xml.sax.saxutils import escape
from hashlib import md5

try:
	basestring
	is_py3 = False

	def py2_encode_utf8(text):
		return text.encode('utf-8', 'ignore')

	def py2_decode_utf8(text):
		return text.decode('utf-8', 'ignore')

except NameError:
	is_py3 = True

	def py2_encode_utf8(text):
		return text

	def py2_decode_utf8(text):
		return text

EPGIMPORT_SOURCES_CONTENT = '''<?xml version="1.0" encoding="utf-8"?>
<sources>
	<mappings>
		<channel name="{prefix}.channels.xml">
			<url>%s</url>
		</channel>
	</mappings>
	<sourcecat sourcecatname="{name}">
		<source type="gen_xmltv" channels="{prefix}.channels.xml">
			<description>{name}</description>
			<url>%s</url>
		</source>
	</sourcecat>
</sources>
'''

EPGLOAD_SOURCES_CONTENT = '''<?xml version="1.0" encoding="utf-8"?>
<sources>
	<sourcecat sourcecatname="{name} XMLTV">
		<source type="gen_xmltv" nocheck="1" channels="//localhost%s">
			<description>{name}</description>
			<url>//localhost%s</url>
		</source>
	</sourcecat>
</sources>
'''

# #################################################################################################

try:
	import unidecode

	def strip_accents(s):
		return unidecode.unidecode(s)

except:
	import unicodedata

	def strip_accents(s):
		return ''.join(c for c in unicodedata.normalize('NFD', py2_decode_utf8(s)) if unicodedata.category(c) != 'Mn')

# #################################################################################################


def _log_dummy(message):
	pass


class XmlEpgGeneratorTemplate:

	def __init__(self, log_info=None, log_error=None):
		# configuration to make this class little bit reusable also in other addons
		self.data_valid_time = ((20 * 3600) - 60) # refresh data every 20 hours by default
		self.data_mtime = 0
		self.log_info = log_info if log_info else _log_dummy
		self.log_error = log_error if log_error else _log_dummy

		self.data_file = '%s.data.xml' % self.prefix
		self.channels_file = '%s.channels.xml' % self.prefix

		# settings for EPGImport
		self.epgimport_sources_file = '/etc/epgimport/%s.sources.xml' % self.prefix
		self.epgimport_settings_file = '/etc/enigma2/epgimport.conf'
		self.epgimport_sources_content = EPGIMPORT_SOURCES_CONTENT.format(prefix=self.prefix, name=self.name)

		# parameters for EPGLoad
		self.epgload_sources_file = '/etc/epgload/.sources.xml'
		self.epgload_settings_file = '/etc/epgload/epgimport.conf'
		self.epgload_sources_content = EPGLOAD_SOURCES_CONTENT.format(name=self.name)

		# Child class must define these values 
#		self.prefix = "o2tv"
#		self.name = "O2TV"
#		self.sid_start = 0xE000
#		self.tid = 5
#		self.onid = 2
#		self.namespace = 0xE030000
	
	# #################################################################################################
	# overide this function to store data modification time somewere else
	
	def get_datafile_mtime(self, data_file):
		try:
			if self.data_mtime == 0:
				self.data_mtime = os.path.getmtime(data_file)

			return self.data_mtime
		except:
			return 0

	# #################################################################################################

	def check_plugin_existence(self, plugin_name):
		file = '/usr/lib/enigma2/python/Plugins/Extensions/%s/__init__.py' % plugin_name
		if os.path.exists(file) or os.path.exists(file + 'o') or os.path.exists(file + 'c'):
			return True

		return False

	# #################################################################################################

	def run(self, force=False, xmlepg_dir=None, xmlepg_days=5):
		if not xmlepg_dir:
			self.log_error("No destination directory for XMLEPG is set")
			return

		# check if epgimport plugin exists
		epgimport_found = self.check_plugin_existence('EPGImport')
		epgload_found = self.check_plugin_existence('EPGLoad')

		if not epgimport_found and not epgload_found:
			self.log_error("Neither EPGImport nor EPGLoad plugin not detected")
			return
			
		# create paths to export files
		data_file = os.path.join(xmlepg_dir, self.data_file)
		channels_file = os.path.join(xmlepg_dir, self.channels_file)

		# check modification time of last exported file
		data_mtime = self.get_datafile_mtime(data_file)

		if not force and (data_mtime + self.data_valid_time) >= time():
			# we have generated data file less then 23 hours
			return

		# time to generate new XML EPG file
		try:
			gen_time_start = time()
			self.create_xmlepg(data_file, channels_file, xmlepg_days)
			self.log_info("EPG generated in %d seconds" % int(time() - gen_time_start))
		except Exception as e:
			self.log_error("Something's failed by generating epg")
			self.log_error(traceback.format_exc())

			# XML data are probably corrupted, so remove it
			try:
				os.remove(data_file)
			except:
				pass

			try:
				os.remove(channels_file)
			except:
				pass

			return
	
		# generate proper sources file for EPGImport
		if epgimport_found and not os.path.exists('/etc/epgimport'):
			os.mkdir('/etc/epgimport')
	
		# generate proper sources file for EPGLoad
		if epgload_found and not os.path.exists('/etc/epgload'):
			os.mkdir('/etc/epgload')

		epgplugin_data_list = []

		if epgimport_found:
			epgplugin_data_list.append((self.epgimport_sources_content, self.epgimport_sources_file, self.epgimport_settings_file))

		if epgload_found:
			epgplugin_data_list.append((self.epgload_sources_content, self.epgload_sources_file, self.epgload_settings_file))
	
		for epgplugin_data in epgplugin_data_list:
			xmlepg_source_content = epgplugin_data[0] % (channels_file, data_file)
			xmlepg_source_content_md5 = md5(xmlepg_source_content.encode('utf-8')).hexdigest()

			# check for correct content of sources file and update it if needed
			if not os.path.exists(epgplugin_data[1]) or md5(open(epgplugin_data[1], 'rb').read()).hexdigest() != xmlepg_source_content_md5:
				self.log_info("Writing new sources file to " + epgplugin_data[1])
				with open(epgplugin_data[1], 'w') as f:
					f.write(xmlepg_source_content)

			# check if source is enabled in epgimport settings and enable if needed
			if os.path.exists(epgplugin_data[2]):
				epgimport_settings = pickle.load(open(epgplugin_data[2], 'rb'))
			else:
				epgimport_settings = { 'sources': [] }

			if self.name not in epgimport_settings['sources']:
				self.log_info("Enabling %s in epgimport/epgload config %s" % (self.name, epgplugin_data[2]))
				epgimport_settings['sources'].append(self.name)
				pickle.dump(epgimport_settings, open(epgplugin_data[2], 'wb'), pickle.HIGHEST_PROTOCOL)

	# #################################################################################################

	def get_channels(self):
		'''
		Tou need to implement this to get list of channels included in XML-EPG file
		Each channel is a map with these requiered fields:
		{
			'name': "channel name",
			'id': 'unique numeric id of channel'
			'id_content': 'unique string representation of channel - only letters, numbers and _ are allowed.' # optional - if not provided, it will be generated from name
		}
		'''
		return []

	# #################################################################################################

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
		return []

	# #################################################################################################

	def create_id_content(self, channel):
		return strip_accents(channel['name']).replace(' ', '_').replace('"', '').replace("'", '').replace(':', '').replace('/', '').replace('.', '').replace('&', '').replace('#', '').replace('@', '') + '_' + str(channel['id'])

	# #################################################################################################

	def create_xmlepg(self, data_file, channels_file, days):

		fromts = int(time())
		tots = fromts + (int(days) * 86400)

		xmlname_prefix = strip_accents(self.name.replace(' ', '')) + '_'

		with open(channels_file, "w") as fc:
			with open(data_file, "w") as f:
				fc.write('<?xml version="1.0" encoding="UTF-8"?>\n')
				fc.write('<channels>\n')

				f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
				f.write('<tv generator-info-name="%s" generator-info-url="https://%s.cz" generator-info-partner="none">\n' % (self.name, self.prefix))

				for channel in self.get_channels():
					self.log_info("Processing EPG for channel: %s" % channel['name'])

					if 'id_content' in channel:
						id_content = xmlname_prefix + channel["id_content"]
					else:
						id_content = xmlname_prefix + self.create_id_content(channel)

					fc.write(' <channel id="%s">1:0:1:%X:%X:%X:%X:0:0:0:http%%3a//</channel>\n' % (id_content, self.sid_start + channel['id'], self.tid, self.onid, self.namespace))

					for event in self.get_epg(channel, fromts, tots):
						try:
							xml_data = {
								'start': datetime.utcfromtimestamp(event['start']).strftime('%Y%m%d%H%M%S') + ' 0000',
								'stop': datetime.utcfromtimestamp(event['end']).strftime('%Y%m%d%H%M%S') + ' 0000',
								'title': escape(str(event['title'])),
								'desc': escape(event['desc']) if event.get('desc') != None else ' '
							}
							f.write(' <programme start="%s" stop="%s" channel="%s">\n' % (xml_data['start'], xml_data['stop'], id_content))
							f.write('  <title lang="cs">%s</title>\n' % xml_data['title'])
							f.write('  <desc lang="cs">%s</desc>\n' % xml_data['desc'])
							f.write(' </programme>\n')
						except:
							self.log_error(traceback.format_exc())
							pass

				fc.write('</channels>\n')
				f.write('</tv>\n')
				
	# #################################################################################################

