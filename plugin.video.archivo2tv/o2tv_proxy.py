# -*- coding: utf-8 -*-
import sys,os,re,traceback
sys.path.append( os.path.dirname(__file__) )

import threading
try:
	from SocketServer import ThreadingMixIn
	from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
	from urllib import unquote
	import cPickle as pickle
	is_py3 = False
	
	def py2_decode_utf8( text ):
		return text.decode('utf-8', 'ignore')

except:
	from socketserver import ThreadingMixIn
	from http.server import HTTPServer, BaseHTTPRequestHandler
	from urllib.parse import unquote
	import pickle
	is_py3 = True
	
	def py2_decode_utf8( text ):
		return text

import base64
import requests
import binascii
from time import time, sleep
from datetime import datetime, timedelta
from xml.sax.saxutils import escape
from o2tv import O2tv

try:
	from md5 import new as md5
except:
	from hashlib import md5

service_client=None
data_mtime = 0

PROXY_PORT=18082
PROXY_VER='1'
NAME_PREFIX="o2tv"
NAME = "O2TV"
ADDON_NAME='plugin.video.archivo2tv'

SERVICEREF_SID_START = 0xE000
SERVICEREF_TID = 5
SERVICEREF_ONID = 2
SERVICEREF_NAMESPACE = 0xE030000

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

def _log(message):
	if is_py3:
		print('[O2TV-XMLEPG] ' + message)
	else:
		print('[O2TV-XMLEPG] ' + message.encode('utf-8'))
		
	try:
		with open('/tmp/%s_proxy.log' % NAME_PREFIX, 'a') as f:
			dtn = datetime.now()
			f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " %s\n" % message)
	except:
		pass

# #################################################################################################

def load_settings():
	settings = {
		'username': '',
		'password': '',
		'deviceid': '',
		'devicename': 'tvbox',
		'enable_xmlepg': False,
		'xmlepg_dir': '/media/hdd',
		'xmlepg_days': 5
	}
	
	config_prefix = "config.plugins.archivCZSK.archives.%s." % ADDON_NAME.replace('.', '_')
	config_prefix_len = len(config_prefix)
	
	with open( "/etc/enigma2/settings", "r" ) as f:
		for line in f.readlines():
			if line.startswith(config_prefix) == True:
				line = line[config_prefix_len:].strip()
				
				if line.startswith("deviceid=") == True:
					settings['deviceid'] = line[9:]
				elif line.startswith("devicename=") == True:
					settings['devicename'] = line[11:]
				elif line.startswith("username=") == True:
					settings['username'] = line[9:]
				elif line.startswith("password=") == True:
					settings['password'] = line[9:]
				elif line.startswith("enable_xmlepg=") == True:
					settings['enable_xmlepg'] = True if line[14:].lower() == 'true' else False
				elif line.startswith("xmlepg_dir=") == True:
					d = line[11:]
					if len(d) > 0:
						settings['xmlepg_dir'] = d
				elif line.startswith("xmlepg_days=") == True:
					try:
						d = int(line[12:])+1
						if d >= 1 and d <= 7:
							settings['xmlepg_days'] = d
					except:
						pass
					
	return settings

# #################################################################################################

def init_service_client( settings = None ):
	global service_client
	
	if service_client != None:
		return

	sync_try = 0
	while int(time()) < 1650358276:
		_log("Time not synced yet - trying manual sync")
		
		# time not synced yet - this will cause O2tv init error, so try to sync manualy
		if sync_try > 12:
			break
			
		if sync_try > 0:
			sleep(1)
		
		try:
			os.system( 'rdate -s time.fu-berlin.de' )
		except:
			pass
		
		sync_try += 1
		
	if settings == None:
		settings = load_settings()

	profile_dir =  '/usr/lib/enigma2/python/Plugins/Extensions/archivCZSK/resources/data/%s' % ADDON_NAME
	
	if len(settings['username']) > 0 and len( settings['password'] ) > 0 and len( settings['deviceid'] ) > 0:
		service_client = O2tv( settings['username'], settings['password'], settings['deviceid'], settings['devicename'], profile_dir )
		service_client.refresh_configuration()

# #################################################################################################

def get_live_url( channel_key ):
	init_service_client()
	
	global service_client
	
#	print("key: %s" % channel_key )
	result = service_client.get_live_link(channel_key)
	return result[0]['url']
	
# #################################################################################################

class Handler(BaseHTTPRequestHandler):
	def do_GET(self):
		response = None
		if self.path == "/info":
			response = NAME_PREFIX + "_proxy" + PROXY_VER
		elif self.path == "/reloadconfig":
			global service_client
			service_client = None
			init_service_client()
			response = ""
		elif self.path.startswith('/playlive/'):
			try:
				location = get_live_url( base64.b64decode(self.path[10:]).decode("utf-8") )
			except:
				location = None
				_log( traceback.format_exc())
				
			if location and len(location) > 0:
				self.send_response( 301 )
				self.send_header( 'Location', location )
				self.end_headers()
				return
		
		if response == None:
			self.send_error( 404 )
			return

		if is_py3 == True and isinstance(response, str):
			response = response.encode("utf-8")
		
		self.send_response(200)
		self.end_headers()
		self.wfile.write(response)
		return
	
	def log_message(self, format, *args):
		return

# #################################################################################################

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
	"""Handle requests in a separate thread."""

# #################################################################################################

def create_xmlepg( data_file, channels_file, days ):
	init_service_client()
	
	global service_client
	
	fromts = int(time())*1000
	tots = (int(time()) + (days * 86400)) * 1000

	with open( channels_file, "w" ) as fc:
		with open( data_file, "w" ) as f:
			fc.write('<?xml version="1.0" encoding="UTF-8"?>\n')
			fc.write('<channels>\n')
			
			f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
			f.write('<tv generator-info-name="%s" generator-info-url="https://%s.cz" generator-info-partner="none">\n' % (ADDON_NAME, NAME_PREFIX))

			for channel in service_client.get_channels_sorted():
				id_content = NAME + '_' + strip_accents(channel['key']).replace(' ', '_').replace('"','').replace(':','').replace('/','').replace('.','')
				_log("Processing channel: %s (%s) [%s]" % (channel['name'], channel['key'], id_content))
				
				fc.write( ' <channel id="%s">1:0:1:%X:%X:%X:%X:0:0:0:http%%3a//</channel>\n' % (id_content, SERVICEREF_SID_START + channel['id'], SERVICEREF_TID, SERVICEREF_ONID, SERVICEREF_NAMESPACE))
				
				epg = service_client.get_channel_epg( channel['key'], fromts, tots )
				
				for event in epg:
					try:
						xml_data = {
							'start': datetime.utcfromtimestamp( event['startTimestamp'] / 1000 ).strftime('%Y%m%d%H%M%S') + ' 0000',
							'stop': datetime.utcfromtimestamp( event['endTimestamp'] / 1000 ).strftime('%Y%m%d%H%M%S') + ' 0000',
							'title': escape(str(event['name'])),
							'desc': escape(event['shortDescription']) if event['shortDescription'] != None else None
						}
						f.write( ' <programme start="%s" stop="%s" channel="%s">\n' % (xml_data['start'], xml_data['stop'], id_content ) )
						f.write( '	<title lang="cs">%s</title>\n' % xml_data['title'])
						f.write( '	<desc lang="cs">%s</desc>\n' % xml_data['desc'] )
						f.write( ' </programme>\n')
					except:
						_log( traceback.format_exc())
						pass
						
			fc.write('</channels>\n')
			f.write('</tv>\n')
			
# #################################################################################################

def generate_xmlepg_if_needed():
	settings = load_settings()
	
	if settings['enable_xmlepg'] == False:
		_log("generator is disabled")
		return
	
	init_service_client( settings )
	global service_client, data_mtime
	
	if service_client == None:
		_log("No login credentials provided or they are wrong")
		return
	
	# check if epgimport plugin exists
	epgimport_check_file = '/usr/lib/enigma2/python/Plugins/Extensions/EPGImport/__init__.py'

	if os.path.exists( epgimport_check_file ) or os.path.exists( epgimport_check_file + 'o' ) or os.path.exists( epgimport_check_file + 'c' ):
		epgimport_found = True
	else:
		_log("EPGImport plugin not detected")
		epgimport_found = False

	# check if epgimport plugin exists
	epgload_check_file = '/usr/lib/enigma2/python/Plugins/Extensions/EPGLoad/__init__.py'

	if os.path.exists( epgload_check_file ) or os.path.exists( epgload_check_file + 'o' ) or os.path.exists( epgload_check_file + 'c' ):
		epgload_found = True
	else:
		_log("EPGLoad plugin not detected")
		epgload_found = False
	
	if not epgimport_found and not epgload_found:
		_log("Neither EPGImport nor EPGLoad plugin not detected")
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
	
	# time to generate new XML EPG file
	try:
		gen_time_start = time()
		create_xmlepg(data_file, channels_file, settings['xmlepg_days'])
		data_mtime = time()
		_log("Epg generated in %d seconds" % int(data_mtime - gen_time_start))
	except Exception as e:
		_log("something's failed by generating epg")
		_log(traceback.format_exc())

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
			_log("Writing new sources file to " + epgplugin_data[1] )
			with open( epgplugin_data[1], 'w' ) as f:
				f.write( xmlepg_source_content )
	
		# check if source is enabled in epgimport settings and enable if needed
		if os.path.exists( epgplugin_data[2] ):
			epgimport_settings = pickle.load(open(epgplugin_data[2], 'rb'))
		else:
			epgimport_settings = { 'sources': [] }
	
		if NAME not in epgimport_settings['sources']:
			_log("Enabling %s in epgimport/epgload config %s" % (NAME, epgplugin_data[2]) )
			epgimport_settings['sources'].append(NAME)
			pickle.dump(epgimport_settings, open(epgplugin_data[2], 'wb'), pickle.HIGHEST_PROTOCOL)

	
# #################################################################################################

class EpgThread(threading.Thread):
	def __init__(self, event):
		threading.Thread.__init__(self)
		self.stopped = event

	def run(self):
		# after boot system time can be inacurate and this causes problems with modification times
		# so set wait time to 10s and periodicaly check to system time sync
		wait_time = 10
		
		while not self.stopped.wait(wait_time):
			# some magic to check, if system time was already synced
			if int(time()) < 1650358276:
				_log("System time not synced yet - waiting ...")
				continue
			
			try:
				generate_xmlepg_if_needed()
			except:
				_log("EPG export failed:")
				_log( traceback.format_exc())
			
			# let's repeat this check every hour
			wait_time = 3600
		
		_log("EPG thread stopped")

# #################################################################################################

pidfile="/tmp/%s_proxy.pid" % NAME_PREFIX

if __name__ == '__main__':
	address = "127.0.0.1"
	port = PROXY_PORT
	
	this_proxy_url = "http://%s:%d" % (address, port)
	
	server = ThreadedHTTPServer(( address, port ), Handler)
	
	with open( pidfile,"w" ) as f:
		f.write( "%d" % os.getpid() )
	
	try:
		init_service_client()
	except:
		_log( "Failed to init %s client" % NAME )
		_log(traceback.format_exc())
	
	# start EPG update thread
	epg_stop_flag = threading.Event()
	epg_thread = EpgThread(epg_stop_flag)
	epg_thread.start()

	try:
		server.serve_forever(3)
	except:
		pass

	epg_stop_flag.set()
	_log("Waiting for EPG thread to stop")
	epg_thread.join()
	
	try:
		os.remove( pidfile )
	except:
		pass
	
	try:
		# after addon update exec permission is lost, so restore it
		os.chmod( os.path.dirname(__file__) + '/' + NAME_PREFIX + '_proxy.sh', 0o755 )
	except:
		pass
	