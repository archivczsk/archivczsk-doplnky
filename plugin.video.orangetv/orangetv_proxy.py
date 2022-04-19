# -*- coding: utf-8 -*-
import sys,os,re,traceback
sys.path.append( os.path.dirname(__file__) )

import threading
try:
	from SocketServer import ThreadingMixIn
	from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
	import cPickle as pickle
	is_py3 = False
except:
	from socketserver import ThreadingMixIn
	from http.server import HTTPServer, BaseHTTPRequestHandler
	import pickle
	is_py3 = True

import requests
import binascii
from time import time
from datetime import datetime, timedelta
from xml.sax.saxutils import escape
from orangetv import OrangeTV

try:
	from md5 import new as md5
except:
	from hashlib import md5

orangetv=None
data_mtime = 0

PROXY_VER='1'

XMLEPG_DATA_FILE = 'orangetv.data.xml'
XMLEPG_CHANNELS_FILE = 'orangetv.channels.xml'

# settings for EPGImport

EPGIMPORT_SOURCES_FILE = '/etc/epgimport/orangetv.sources.xml'
EPGIMPORT_SETTINGS_FILE = '/etc/enigma2/epgimport.conf'

EPGIMPORT_SOURCES_CONTENT ='''<?xml version="1.0" encoding="utf-8"?>
<sources>
  <mappings>
	  <channel name="orangetv.channels.xml">
		<url>%s</url>
	  </channel>
  </mappings>
  <sourcecat sourcecatname="OrangeTV">
	<source type="gen_xmltv" channels="orangetv.channels.xml">
	  <description>OrangeTV</description>
	  <url>%s</url>
	</source>
  </sourcecat>
</sources>
'''

# parameters for EPGLoad

EPGLOAD_SOURCES_FILE = '/etc/epgload/orangetv.sources.xml'
EPGLOAD_SETTINGS_FILE = '/etc/epgload/epgimport.conf'

EPGLOAD_SOURCES_CONTENT ='''<?xml version="1.0" encoding="utf-8"?>
<sources>
	<sourcecat sourcecatname="OrangeTV XMLTV">
		<source type="gen_xmltv" nocheck="1" channels="//localhost%s">
			<description>OrangeTV</description>
			<url>//localhost%s</url>
		</source>
	</sourcecat>
</sources>
'''

# #################################################################################################

def _log(message):
	print(message)
	try:
		with open('/tmp/orangetv_proxy.log', 'a') as f:
			dtn = datetime.now()
			f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " %s\n" % message)
	except:
		pass

# #################################################################################################

def load_settings():
	settings = {
		'orangetvuser': '',
		'orangetvpwd': '',
		'deviceid': 'Nexus7',
		'enable_xmlepg': False,
		'xmlepg_dir': '/media/hdd',
		'xmlepg_days': 5
	}
	
	with open( "/etc/enigma2/settings", "r" ) as f:
		for line in f.readlines():
			if line.startswith("config.plugins.archivCZSK.archives.plugin_video_orangetv.") == True:
				line = line[57:].strip()
				
				if line.startswith("deviceid=") == True:
					settings['deviceid'] = line[9:]
				elif line.startswith("orangetvuser=") == True:
					settings['orangetvuser'] = line[13:]
				elif line.startswith("orangetvpwd=") == True:
					settings['orangetvpwd'] = line[12:]
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

def init_orangetv( settings = None ):
	global orangetv
	
	if orangetv != None:
		return

	if settings == None:
		settings = load_settings()

	profile_dir =  '/usr/lib/enigma2/python/Plugins/Extensions/archivCZSK/resources/data/plugin.video.orangetv'
	
	if len(settings['orangetvuser']) > 0 and len( settings['orangetvpwd'] ) > 0:
		orangetv = OrangeTV( settings['orangetvuser'], settings['orangetvpwd'], settings['deviceid'], profile_dir )
		orangetv.refresh_access_token()

# #################################################################################################

def get_live_url( channel_key ):
	init_orangetv()
	
	global orangetv
	
	result = orangetv.getVideoLink(channel_key + '|||')
	return result[0]['url']
	
# #################################################################################################

class Handler(BaseHTTPRequestHandler):
	def do_GET(self):
		response = None
		if self.path == "/info":
			response = "orangetv_proxy" + PROXY_VER
		elif self.path == "/reloadconfig":
			global orangetv
			orangetv = None
			init_orangetv()
			response = ""
		elif self.path.startswith('/playlive/'):
			try:
				location = get_live_url( self.path[10:])
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
	init_orangetv()
	
	global orangetv
	
	fromts = int(time())*1000
	tots = (int(time()) + (days * 86400)) * 1000

	with open( channels_file, "w" ) as fc:
		with open( data_file, "w" ) as f:
			fc.write('<?xml version="1.0" encoding="UTF-8"?>\n')
			fc.write('<channels>\n')
			
			f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
			f.write('<tv generator-info-name="plugin.video.orangetv" generator-info-url="https://orangetv.sk" generator-info-partner="none">\n')

			for channel in orangetv.live_channels():
				_log("Processing channel: %s (%s)" % (channel.name, channel.channel_key))

				id_content = 'OrangeTV_' + channel.channel_key
				fc.write( ' <channel id="%s">1:0:1:%X:0:0:E020000:0:0:0:http%%3a//</channel>\n' % (id_content, channel.id))
				
				epg = orangetv.getChannelEpg( channel.channel_key, fromts, tots )
				# save 1 day to epg cache for usage in the addon
				orangetv.fillChannelEpgCache(channel.channel_key, epg, fromts + (24 * 3600 * 1000))
				
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
			orangetv.saveEpgCache()
			# save some memory
			orangetv.epg_cache = {}
			
# #################################################################################################

def generate_xmlepg_if_needed():
	settings = load_settings()
	
	if settings['enable_xmlepg'] == False:
		_log("[ORANGE-XMLEPG] generator is disabled")
		return
	
	init_orangetv( settings )
	global orangetv, data_mtime
	
	if orangetv == None:
		_log("[ORANGE-XMLEPG] No orangetv login credentials provided or they are wrong")
		return
	
	# check if epgimport plugin exists
	epgimport_check_file = '/usr/lib/enigma2/python/Plugins/Extensions/EPGImport/__init__.py'

	if os.path.exists( epgimport_check_file ) or os.path.exists( epgimport_check_file + 'o' ) or os.path.exists( epgimport_check_file + 'c' ):
		epgimport_found = True
	else:
		_log("[ORANGE-XMLEPG] EPGImport plugin not detected")
		epgimport_found = False

	# check if epgimport plugin exists
	epgload_check_file = '/usr/lib/enigma2/python/Plugins/Extensions/EPGLoad/__init__.py'

	if os.path.exists( epgload_check_file ) or os.path.exists( epgload_check_file + 'o' ) or os.path.exists( epgload_check_file + 'c' ):
		epgload_found = True
	else:
		_log("[ORANGE-XMLEPG] EPGLoad plugin not detected")
		epgload_found = False
	
	if not epgimport_found and not epgload_found:
		_log("[ORANGE-XMLEPG] Neither EPGImport nor EPGLoad plugin not detected")
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
		_log("[ORANGE-XMLEPG] Epg generated in %d seconds" % int(data_mtime - gen_time_start))
	except Exception as e:
		_log("[ORANGE-XMLEPG] something's failed by generating epg")
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
			_log("[ORANGE-XMLEPG] Writing new sources file to " + epgplugin_data[1] )
			with open( epgplugin_data[1], 'w' ) as f:
				f.write( xmlepg_source_content )
	
		# check if orange source is enabled in epgimport settings and enable if needed
		if os.path.exists( epgplugin_data[2] ):
			epgimport_settings = pickle.load(open(epgplugin_data[2], 'rb'))
		else:
			epgimport_settings = { 'sources': [] }
	
		if 'OrangeTV' not in epgimport_settings['sources']:
			_log("[ORANGE-XMLEPG] Enabling OrangeTV in epgimport/epgload config %s" % epgplugin_data[2] )
			epgimport_settings['sources'].append('OrangeTV')
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
				_log("[ORANGE-XMLEPG] System time not synced yet - waiting ...")
				continue
			
			try:
				generate_xmlepg_if_needed()
			except:
				_log("[ORANGE-XMLEPG] EPG export failed:")
				_log( traceback.format_exc())
			
			# let's repeat this check every hour
			wait_time = 3600
		
		_log("[ORANGE-XMLEPG] EPG thread stopped")

# #################################################################################################

pidfile="/tmp/orangetv_proxy.pid"

if __name__ == '__main__':
	address = "127.0.0.1"
	port = 18081
	
	this_proxy_url = "http://%s:%d" % (address, port)
	
	server = ThreadedHTTPServer(( address, port ), Handler)
	
	with open( pidfile,"w" ) as f:
		f.write( "%d" % os.getpid() )
	
	init_orangetv()
	
	# start EPG update thread
	epg_stop_flag = threading.Event()
	epg_thread = EpgThread(epg_stop_flag)
	epg_thread.start()

	try:
		server.serve_forever(3)
	except:
		pass

	epg_stop_flag.set()
	_log("[ORANGE-XMLEPG] Waiting for EPG thread to stop")
	epg_thread.join()
	
	try:
		os.remove( pidfile )
	except:
		pass
	
	try:
		# after addon update exec permission is lost, so restore it
		os.chmod( os.path.dirname(__file__) + '/orangetv_proxy.sh', 0o755 )
	except:
		pass
	