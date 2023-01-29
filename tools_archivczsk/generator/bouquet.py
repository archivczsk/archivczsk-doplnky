# -*- coding: utf-8 -*-

import sys, os, re, io, base64
import threading, requests
from .lamedb import lameDB

try:
	from urllib import quote
except:
	from urllib.parse import quote
	
# #################################################################################################

class BouquetGeneratorTemplate:

	def __init__(self, endpoint, enable_adult=True, enable_xmlepg=False, enable_picons=False, player_name='0', user_agent=None):
		# configuration to make this class little bit reusable also in other addons
		self.proxy_url = endpoint
		self.userbouquet_file_name = "userbouquet.%s.tv" % self.prefix
		self.play_url_pattern = '/playlive/%s'
		self.user_agent = user_agent
		self.enable_adult = enable_adult
		self.enable_xmlepg = enable_xmlepg
		self.enable_picons = enable_picons
		self.player_name = player_name

		# Child class must define these values 
#		self.prefix = "o2tv"
#		self.name = "O2TV"
#		self.sid_start = 0xE000
#		self.tid = 5
#		self.onid = 2
#		self.namespace = 0xE030000

	# #################################################################################################
	
	@staticmethod
	def download_picons(picons):
		def download_picon(fileout, url):
			if not url.endswith('.png'):
				return
			
			if not os.path.exists(fileout):
				try:
					r = requests.get( url, timeout=5 )
					if r.status_code == 200:
						with open(fileout, 'wb') as f:
							f.write( r.content )
				except:
					pass

		
		if not os.path.exists( '/usr/share/enigma2/picon' ):
			os.mkdir('/usr/share/enigma2/picon')
			
		for ref in picons:
			urls = picons[ref]

			fileout = '/usr/share/enigma2/picon/' + ref + '.png'
			
			if isinstance(urls, (type(()), type([]))):
				for url in urls:
					download_picon( fileout, url)
			else:
				download_picon( fileout, urls)
			
	# #################################################################################################
	
	def reload_bouquets(self):
		session_id = None
		
		try:
			# on DMM there is a security check, so try to get session ID first
			response = requests.post("http://127.0.0.1/web/session")
			
			if response.status_code == 200:
				data = response.text
				s1=data.find('<e2sessionid>')
				s2=data.find('</e2sessionid>')
				
				if s1 != -1 and s2 != -1:
					session_id = data[s1+13:s2]
		except:
			pass
		
		try:
			if session_id:
				requests.post("http://127.0.0.1/web/servicelistreload?mode=2&sessionid=%s" % session_id)
			else:
				requests.get("http://127.0.0.1/web/servicelistreload?mode=2")
		except:
			pass

	# #################################################################################################
	
	def userbouquet_exists(self):
		return os.path.exists(os.path.join("/etc/enigma2/", self.userbouquet_file_name))
	
	# #################################################################################################
	
	def userbouquet_remove(self):
		if not self.userbouquet_exists():
			return False
		
		ub_service_ref = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "' + self.userbouquet_file_name + '" ORDER BY bouquet'
		
		with open( "/etc/enigma2/bouquets.tv.temporary", "w" ) as fw:
			with open( "/etc/enigma2/bouquets.tv", "r" ) as f:
				for line in f.readlines():
					if not line.startswith(ub_service_ref):
						fw.write(line)

		os.rename("/etc/enigma2/bouquets.tv.temporary", "/etc/enigma2/bouquets.tv")
		
		os.remove( "/etc/enigma2/" + self.userbouquet_file_name )
		self.reload_bouquets()
		return True
	
	# #################################################################################################
	
	def build_service_ref( self, service, player_id ):
		return player_id + ":0:{:X}:{:X}:{:X}:{:X}:{:X}:0:0:0:".format( service.ServiceType, service.ServiceID, service.Transponder.TransportStreamID, service.Transponder.OriginalNetworkID, service.Transponder.DVBNameSpace )

	# #################################################################################################
	
	def service_ref_get( self, lamedb, channel_name, player_id, channel_id ):
		
		skylink_freq = [ 11739, 11778, 11856, 11876, 11934, 11954, 11973, 12012, 12032, 12070, 12090, 12110, 12129, 12168, 12344, 12363 ]
		antik_freq = [ 11055, 11094, 11231, 11283, 11324, 11471, 11554, 11595, 11637, 12605 ]
		
		def cmp_freq( f, f_list ):
			f = int(f/1000)
			
			for f2 in f_list:
				if abs( f - f2) < 5:
					return True
		
			return False
	
		if lamedb != None:
			try:
				services = lamedb.Services[ lamedb.name_normalise( channel_name ) ]
				
				# try position 23.5E first
				for s in services:
					if s.Transponder.Data.OrbitalPosition == 235 and cmp_freq( s.Transponder.Data.Frequency, skylink_freq ):
						return self.build_service_ref(s, player_id)
		
				# then 16E
				for s in services:
					if s.Transponder.Data.OrbitalPosition == 160 and cmp_freq( s.Transponder.Data.Frequency, antik_freq ):
						return self.build_service_ref(s, player_id)
		
				for s in services:
					if s.Transponder.Data.OrbitalPosition == 235:
						return self.build_service_ref(s, player_id)
		
				# then 16E
				for s in services:
					if s.Transponder.Data.OrbitalPosition == 160:
						return self.build_service_ref(s, player_id)
		
				# then 0,8W
				for s in services:
					if s.Transponder.Data.OrbitalPosition == -8:
						return self.build_service_ref(s, player_id)
		
				# then 192
				for s in services:
					if s.Transponder.Data.OrbitalPosition == 192:
						return self.build_service_ref(s, player_id)
		
				# take the first one
				for s in services:
					return self.build_service_ref(s, player_id)
		
			except:
				pass
		
		return player_id + ":0:1:%X:%X:%X:%X:0:0:0:" % (self.sid_start + channel_id, self.tid, self.onid, self.namespace)
	
	# #################################################################################################
	
	def encode_channel_key(self, key):
		return base64.b64encode(key.encode('utf-8')).decode('utf-8')

	# #################################################################################################

	'''
	Implement this function to return list of channels
	'''
	def get_channels(self):
		return []

	# #################################################################################################

	def run(self):
		# if epg generator is disabled, then try to create service references based on lamedb
		if self.enable_xmlepg:
			lamedb = None
		else:
			lamedb = lameDB("/etc/enigma2/lamedb")
		
		if self.player_name == "1": # gstplayer
			player_id = "5001"
		elif self.player_name == "2": # exteplayer3
			player_id = "5002"
		elif self.player_name == "3": # DMM
			player_id = "8193"
		elif self.player_name == "4": # DVB service (OE >=2.5)
			player_id = "1"
		else:
			player_id = "4097" # system default
	
		picons = {}
		
		service_ref_uniq = ':%X:%X:%X:0:0:0:' % (self.tid, self.onid, self.namespace)
		
		with open("/etc/enigma2/" + self.userbouquet_file_name, "w") as f:
			f.write("#NAME %s\n" % self.name)

			for channel in self.get_channels():
				if not self.enable_adult and channel.get('adult', False):
					continue

				if channel.get('is_separator', False):
					f.write("#SERVICE 1:64:0:0:0:0:0:0:0:0::" + channel['name'] + "\n")
					f.write("#DESCRIPTION " + channel['name'] + "\n")
					continue

				channel_name = channel['name']
				url = self.proxy_url + (self.play_url_pattern % self.encode_channel_key(channel['key']))

				if self.user_agent:
					url += '#User-Agent=%s' % self.user_agent

				url = quote(url)

				service_ref = self.service_ref_get(lamedb, channel_name, player_id, channel['id'])

				f.write("#SERVICE " + service_ref + url + ":" + channel_name + "\n")
				f.write("#DESCRIPTION " + channel_name + "\n")

				try:
					if enable_picons and service_ref.endswith(service_ref_uniq):
						picons[ service_ref[:-1].replace(':', '_') ] = channel['picon']
				except:
					pass

		first_export = True
		with open("/etc/enigma2/bouquets.tv", "r") as f:
			for line in f.readlines():
				if self.userbouquet_file_name in line:
					first_export = False
					break

		if first_export:
			with open("/etc/enigma2/bouquets.tv", "a") as f:
				f.write('#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "' + self.userbouquet_file_name + '" ORDER BY bouquet' + "\n")

		self.reload_bouquets()
			
		if self.enable_picons:
			threading.Thread(target=BouquetGeneratorTemplate.download_picons,args=(picons,)).start()

	# #################################################################################################
	