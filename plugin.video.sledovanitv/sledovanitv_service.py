# -*- coding: utf-8 -*-
import json
import sys
import os
import traceback
import threading, requests
from Plugins.Extensions.archivCZSK.engine.service_helper import StartAddonServiceHelper, AddonServiceHelper
from Plugins.Extensions.archivCZSK.engine.tools.bouquet_generator import BouquetGeneratorTemplate
from twisted.internet.defer import inlineCallbacks, returnValue
try:
	from urllib import quote
	is_py3 = False
	def py2_decode_utf8( text ):
		return text.decode('utf-8', 'ignore')

except:
	from urllib.parse import quote
	is_py3 = True
	
	def py2_decode_utf8( text ):
		return text


sys.path.append( os.path.dirname(__file__) )

try:
	import cPickle as pickle
except:
	import pickle

import base64
from time import time
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape
from sledovanitv import SledovaniTvCache

try:
	from md5 import new as md5
except:
	from hashlib import md5

data_mtime = 0

EPG_GENERATOR_RUN_TIME=3600

NAME_PREFIX="sledovanitv"
NAME = "SledovaniTV"
ADDON_NAME='plugin.video.sledovanitv'

SERVICEREF_SID_START = 0x500
SERVICEREF_TID = 0xA0
SERVICEREF_ONID = 12
SERVICEREF_NAMESPACE = 0xAB40000

XMLEPG_DATA_FILE = '%s.data.xml' % NAME_PREFIX
XMLEPG_CHANNELS_FILE = '%s.channels.xml' % NAME_PREFIX

# settings for EPGImport

EPGIMPORT_SOURCES_FILE = '/etc/epgimport/%s.sources.xml' % NAME_PREFIX
EPGIMPORT_SETTINGS_FILE = '/etc/enigma2/epgimport.conf'

EPGIMPORT_SOURCES_CONTENT ='''<?xml version="1.0" encoding="utf-8"?>
<sources>
  <mappings>
	  <channel name="{}.channels.xml">
		<url>%s</url>
	  </channel>
  </mappings>
  <sourcecat sourcecatname="{}">
	<source type="gen_xmltv" channels="{}.channels.xml">
	  <description>{}</description>
	  <url>%s</url>
	</source>
  </sourcecat>
</sources>
'''.format( NAME_PREFIX, NAME, NAME_PREFIX, NAME )

# parameters for EPGLoad

EPGLOAD_SOURCES_FILE = '/etc/epgload/.sources.xml'
EPGLOAD_SETTINGS_FILE = '/etc/epgload/epgimport.conf'

EPGLOAD_SOURCES_CONTENT ='''<?xml version="1.0" encoding="utf-8"?>
<sources>
	<sourcecat sourcecatname="{} XMLTV">
		<source type="gen_xmltv" nocheck="1" channels="//localhost%s">
			<description>{}</description>
			<url>//localhost%s</url>
		</source>
	</sourcecat>
</sources>
'''.format( NAME, NAME )

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

class SledovaniTvBouquetGenerator(BouquetGeneratorTemplate):
	def __init__(self, endpoint):
		# configuration to make this class little bit reusable also in other addons
		self.prefix = NAME_PREFIX
		self.name = NAME
		self.sid_start = SERVICEREF_SID_START
		self.tid = SERVICEREF_TID
		self.onid = SERVICEREF_ONID
		self.namespace = SERVICEREF_NAMESPACE
		BouquetGeneratorTemplate.__init__(self, endpoint)
		
# #################################################################################################

def init_sledovanitv( settings ):
	profile_dir = '/usr/lib/enigma2/python/Plugins/Extensions/archivCZSK/resources/data/%s' % ADDON_NAME
	
	if len(settings['username']) > 0 and len( settings['password'] ) > 0:
		try:
			sledovanitv = SledovaniTvCache.get( settings['username'], settings['password'], settings['pin'], settings['serialid'], profile_dir, service_helper.logInfo )
		except Exception as e:
			service_helper.logError("Failed to init Sledovani.TV client: %s" % str(e))
			sledovanitv = None
	else:
		sledovanitv = None
		
	return sledovanitv

# #################################################################################################

def create_xmlepg( sledovanitv, data_file, channels_file, days ):
	
	with open( channels_file, "w" ) as fc:
		with open( data_file, "w" ) as f:
			fc.write('<?xml version="1.0" encoding="UTF-8"?>\n')
			fc.write('<channels>\n')
			
			f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
			f.write('<tv generator-info-name="%s" generator-info-url="https://%s.cz" generator-info-partner="none">\n' % (ADDON_NAME, NAME_PREFIX))

			channels = sledovanitv.get_channels_sorted()
			_, zone = sledovanitv.get_time()
			
			zone = zone.replace('+', ' ')
			
			for channel in channels:
				id_content = NAME + '_' + strip_accents(channel['id']).replace(' ', '_').replace('"','').replace(':','').replace('/','').replace('.','')
				fc.write( ' <channel id="%s">1:0:1:%X:%X:%X:%X:0:0:0:http%%3a//</channel>\n' % (id_content, SERVICEREF_SID_START + channel['number'], SERVICEREF_TID, SERVICEREF_ONID, SERVICEREF_NAMESPACE))

			for day in range(days):
				if day == 0:
					from_datetime = datetime.now() - timedelta(minutes = 60)
					duration_min = int((datetime.combine(date.today()+timedelta(days = 1), datetime.min.time()) - from_datetime).total_seconds() // 60)
				else:
					from_datetime = datetime.combine(date.today()+timedelta(days = day), datetime.min.time())
					duration_min = 1440
					
				epgdata = sledovanitv.get_epg( from_datetime, duration_min )
	
				for channel in channels:
					service_helper.logInfo("Processing EPG for day %d and channel: %s (%s)" % (day, channel['name'], channel['id']))
	
					id_content = NAME + '_' + strip_accents(channel['id']).replace(' ', '_').replace('"','').replace(':','').replace('/','').replace('.','')
	
					for event in epgdata.get(channel['id'], []):
						tr = event['startTime'][11:] + ' - ' + event['endTime'][11:]
						
						if event['title'] in ('Vysílání', 'Vysielanie', 'Vysílání ' + tr, 'Vysielanie ' + tr, tr):
							# filter out garbage ...
							continue
						
						try:
							xml_data = {
								'start': event['startTime'].replace('-', '').replace(' ', '').replace(':', '') + zone,
								'stop': event['endTime'].replace('-', '').replace(' ', '').replace(':', '') + zone,
								'title': escape(str(event['title'])),
								'desc': escape(event['description']) if event['description'] != None and len(event['description']) > 0 else ' '
							}
							f.write( ' <programme start="%s" stop="%s" channel="%s">\n' % (xml_data['start'], xml_data['stop'], id_content ) )
							f.write( '	<title lang="cs">%s</title>\n' % xml_data['title'])
							f.write( '	<desc lang="cs">%s</desc>\n' % xml_data['desc'] )
							f.write( ' </programme>\n')
						except:
							service_helper.logException( traceback.format_exc())
							pass
						
			fc.write('</channels>\n')
			f.write('</tv>\n')
			
# #################################################################################################

def generate_xmlepg_if_needed(settings):
	global generator_running, data_mtime
	
	# check if epgimport plugin exists
	epgimport_check_file = '/usr/lib/enigma2/python/Plugins/Extensions/EPGImport/__init__.py'

	if os.path.exists( epgimport_check_file ) or os.path.exists( epgimport_check_file + 'o' ) or os.path.exists( epgimport_check_file + 'c' ):
		epgimport_found = True
	else:
		service_helper.logDebug("EPGImport plugin not detected")
		epgimport_found = False

	# check if epgimport plugin exists
	epgload_check_file = '/usr/lib/enigma2/python/Plugins/Extensions/EPGLoad/__init__.py'

	if os.path.exists( epgload_check_file ) or os.path.exists( epgload_check_file + 'o' ) or os.path.exists( epgload_check_file + 'c' ):
		epgload_found = True
	else:
		service_helper.logDebug("EPGLoad plugin not detected")
		epgload_found = False
	
	if not epgimport_found and not epgload_found:
		service_helper.logInfo("Neither EPGImport nor EPGLoad plugin not detected")
		return
	
		
	# create paths to export files
	data_file = os.path.join(settings['xmlepg_dir'], XMLEPG_DATA_FILE)
	channels_file = os.path.join(settings['xmlepg_dir'], XMLEPG_CHANNELS_FILE)
	
	# check modification time of last exported file
	try:
		if data_mtime == 0:
			# data_mtime is global to prevent rotary disc to start by every check
			data_mtime = os.path.getmtime( data_file )
			
		if (data_mtime + 82800) >= time():
			# we have generated data file less then 23 hours
			return
	except:
		pass
	
	sledovanitv = init_sledovanitv( settings )
	if sledovanitv == None:
		service_helper.logInfo("No SledovaniTV login credentials provided or they are wrong")
		return

	# time to generate new XML EPG file
	try:
		gen_time_start = time()
		create_xmlepg(sledovanitv, data_file, channels_file, int(settings['xmlepg_days']))
		data_mtime = time()
		service_helper.logInfo("EPG generated in %d seconds" % int(data_mtime - gen_time_start))
	except Exception as e:
		service_helper.logError("Something's failed by generating epg")
		service_helper.logException(traceback.format_exc())
		return

	# generate proper sources file for EPGImport
	if epgimport_found and not os.path.exists('/etc/epgimport'):
		os.mkdir( '/etc/epgimport')

	# generate proper sources file for EPGLoad
	if epgload_found and not os.path.exists('/etc/epgload'):
		os.mkdir( '/etc/epgload')
	
	epgplugin_data_list = []
	
	if epgimport_found:
		epgplugin_data_list.append( (EPGIMPORT_SOURCES_CONTENT, EPGIMPORT_SOURCES_FILE, EPGIMPORT_SETTINGS_FILE) )

	if epgload_found:
		epgplugin_data_list.append( (EPGLOAD_SOURCES_CONTENT, EPGLOAD_SOURCES_FILE, EPGLOAD_SETTINGS_FILE) )

	for epgplugin_data in epgplugin_data_list:
		xmlepg_source_content = epgplugin_data[0] % (channels_file, data_file)
		xmlepg_source_content_md5 = md5( xmlepg_source_content.encode('utf-8') ).hexdigest()
	
		# check for correct content of sources file and update it if needed
		if not os.path.exists( epgplugin_data[1] ) or md5( open( epgplugin_data[1], 'rb' ).read() ).hexdigest() != xmlepg_source_content_md5:
			service_helper.logDebug("Writing new sources file to " + epgplugin_data[1] )
			with open( epgplugin_data[1], 'w' ) as f:
				f.write( xmlepg_source_content )
	
		# check if source is enabled in epgimport settings and enable if needed
		if os.path.exists( epgplugin_data[2] ):
			epgimport_settings = pickle.load(open(epgplugin_data[2], 'rb'))
		else:
			epgimport_settings = { 'sources': [] }
	
		if NAME not in epgimport_settings['sources']:
			service_helper.logInfo("Enabling %s in epgimport/epgload config %s" % (NAME, epgplugin_data[2]) )
			epgimport_settings['sources'].append(NAME)
			pickle.dump(epgimport_settings, open(epgplugin_data[2], 'wb'), pickle.HIGHEST_PROTOCOL)


# #################################################################################################

def print_settings( settings ):
	settings = settings.copy()

	# remove sensitive data from logs
	if 'password' in settings and len(settings['password']) > 0:
		settings['password'] = '***'
	
	return service_helper.logDebug("Received settings: %s" % settings)

# #################################################################################################

epg_generator_running = False

def start_epg_generator(arg):
	if int(time()) < 1650358276:
		# time is not synced yet - wait a little bit and try again
		return service_helper.runDelayed(10, start_epg_generator, None )
	
	global epg_generator_running
	
	if epg_generator_running:
		# do nothing
		return
	
	epg_generator_running = True
	# load actual settings and continue when received
	service_helper.getSettings(['username', 'password', 'pin', 'serialid', 'enable_userbouquet', 'enable_xmlepg', 'xmlepg_dir', 'xmlepg_days'], settings_received_epg )
	
# #################################################################################################

def epg_generator_stop( settings ):
	global epg_generator_running
	epg_generator_running = False

# #################################################################################################

def settings_received_epg( settings ):
	# check received settings
	print_settings( settings )
	
	if not settings['enable_xmlepg'] or not settings['enable_userbouquet']:
		epg_generator_running = False
		service_helper.logDebug("Generating of XMLEPG is disabled")
		service_helper.runDelayed(EPG_GENERATOR_RUN_TIME, start_epg_generator, None )
		return

	if not settings['username'] or not settings['password'] or not settings['serialid'] or not settings['xmlepg_dir']:
		epg_generator_running = False
		service_helper.logError("No login data provided")
		service_helper.runDelayed(EPG_GENERATOR_RUN_TIME, start_epg_generator, None )
		return

	if not settings['xmlepg_dir']:
		epg_generator_running = False
		service_helper.logError("No destination directory for XMLEPG is set")
		service_helper.runDelayed(EPG_GENERATOR_RUN_TIME, start_epg_generator, None )
		return
	
	service_helper.runDelayed(1, (generate_xmlepg_if_needed, epg_generator_stop), settings )
	service_helper.runDelayed(EPG_GENERATOR_RUN_TIME, start_epg_generator, None )

# #################################################################################################	

bouquet_generator_running = False

def start_bouquet_generator(arg):
	act_time = int(time())
	
	if act_time < 1650358276:
		if act_time < 3600:
			# time is not synced yet - wait a little bit and try again
			return service_helper.runDelayed(10, start_bouquet_generator, None )
		else:
			return
	
	try_generate_userbouquet(False)

#def bouquet_generator_stop( settings, endpoint ):
def bouquet_generator_stop( data ):
	global bouquet_generator_running
	bouquet_generator_running = False
	
# #################################################################################################

def try_generate_userbouquet( force=False ):
	global bouquet_generator_running
	
	if bouquet_generator_running:
		# do nothing
		return

	bouquet_generator_running = True
	service_helper.getHttpEndpoint( ADDON_NAME, http_endpoint_received, force=force )
	
# #################################################################################################

def http_endpoint_received( addon_id, endpoint, force ):
	service_helper.logDebug("%s HTTP endpoint received: %s" % (addon_id, endpoint))
	# load actual settings and continue when received
	service_helper.getSettings(['username', 'password', 'pin', 'serialid', 'enable_userbouquet', 'enable_adult', 'enable_xmlepg', 'player_name', 'enable_picons'], settings_received_bouquet, endpoint=endpoint, force=force )

# #################################################################################################

def settings_received_bouquet( settings, endpoint, force ):
	# check received settings
	print_settings( settings )
	
	if not settings['username'] or not settings['password'] or not settings['serialid']:
		bouquet_generator_running = False
		service_helper.logError("No login data provided")
		return
	
	service_helper.runDelayed(1, (generate_userbouquet, bouquet_generator_stop), (settings, endpoint, force) )

# #################################################################################################

def generate_userbouquet( data ):
	settings, endpoint, force = data
	
	obg = SledovaniTvBouquetGenerator( endpoint )
	if not settings['enable_userbouquet']:
		if obg.userbouquet_remove():
			service_helper.logDebug("Userbouquet removed")
			
		return

	sledovanitv = init_sledovanitv( settings )
	
	if sledovanitv and not sledovanitv.check_pairing():
		sledovanitv = None
	
	if sledovanitv == None:
		service_helper.logInfo("No sledovanitv login credentials provided or they are wrong")
		if obg.userbouquet_remove():
			service_helper.logDebug("Userbouquet removed")
		return

	try:	
		channels = []
		service_helper.logDebug("Requesting channel list for userbouquet generator")
		for channel in sledovanitv.get_channels_sorted():
			channels.append({
					'id': channel['number'],
					'key': channel['id'],
					'name': channel['name'],
					'adult': channel['adult'],
					'picon': channel['picon']
				}) 

		service_helper.logDebug("Starting generating of userbouquet")
		if obg.generate_bouquet( channels, settings['enable_adult'], settings['enable_xmlepg'], settings['enable_picons'], settings['player_name'] ):
			service_helper.logDebug("Userbouquet successfuly generated")
		else:
			service_helper.logDebug("No need to regenerate userbouquet")

	except:
		if force:
			msg = "Pri generovaní userbouquetu pre SledovaniTV nastala chyba. Skontrolujte log súbor a zareportujte chybu."
			service_helper.showErrorMessage( msg )
			
		service_helper.logException( traceback.format_exc())
	
	
# #################################################################################################	
	
class SledovaniTvAddonServiceHelper( AddonServiceHelper ):
	def handle_userbouquet_gen(self):
		self.runDelayed(1, try_generate_userbouquet, True )
	
# #################################################################################################

service_helper = StartAddonServiceHelper(SledovaniTvAddonServiceHelper(), start_epg_generator, None)
#service_helper.runDelayed(1, start_bouquet_generator, None )
service_helper.runLoop( 4*3600, start_bouquet_generator, None )
service_helper.run()
