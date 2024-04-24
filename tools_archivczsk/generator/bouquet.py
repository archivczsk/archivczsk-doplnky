# -*- coding: utf-8 -*-

import os, base64
import threading, requests, traceback
from Plugins.Extensions.archivCZSK.engine import client
from .lamedb import lameDB

try:
	from Components.ParentalControl import parentalControl
except:
	class ParentalControl():
		def __init__(self):
			pass

		def open(self):
			pass

		def save(self):
			pass

	parentalControl = ParentalControl()

# #################################################################################################

class BouquetGeneratorTemplate(object):

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
		s = requests.Session()

		def download_picon(fileout, url):
			if not os.path.exists(fileout):
				try:
					r = s.get( url, timeout=5 )

					if r.status_code == 200:
						if r.headers.get('content-type','').lower() != 'image/png':
							client.log.error("Unsupported content type %s of picon URL %s downloaded to %s" % (r.headers.get('content-type'), url, fileout))
						else:
							client.log.debug("Writing picon from URL %s to %s" % (url, fileout))
							with open(fileout, 'wb') as f:
								f.write( r.content )
				except:
					client.log.error(traceback.format_exc())
					pass


		if not os.path.exists( '/usr/share/enigma2/picon' ):
			os.mkdir('/usr/share/enigma2/picon')

		for ref, urls in picons.items():
			fileout = '/usr/share/enigma2/picon/' + ref + '.png'

			if isinstance(urls, (type(()), type([]))):
				for url in urls:
					download_picon( fileout, url)
			elif urls:
				download_picon( fileout, urls)

	# #################################################################################################

	def reload_bouquets(self):
		try:
			# try to reload bouquets directly using enigma
			from enigma import eDVBDB
			eDVBDB.getInstance().reloadBouquets()
			return
		except:
			pass

		# fallback - use webinterface to reload bouquets
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
				requests.post("http://127.0.0.1/web/servicelistreload", data={ 'mode': 2, 'sessionid': session_id })
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

		return player_id + ":0:1:%X:%X:%X:%X:0:0:0:" % ((self.sid_start + channel_id) % 0xFFFF, self.tid, self.onid, self.namespace)

	# #################################################################################################

	def encode_channel_key(self, key):
		return base64.b64encode(key.encode('utf-8')).decode('utf-8')

	# #################################################################################################

	def get_channels(self):
		'''
		Tou need to implement this to get list of channels included to bouquet
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
		return []

	# #################################################################################################

	def load_blacklist(self, service_ref_uniq):
		try:
			parentalControl.save()
		except:
			pass

		blacklist = []
		try:
			with open('/etc/enigma2/blacklist', 'r') as f:
				for line in f:
					if service_ref_uniq not in line:
						blacklist.append(line.strip())
		except:
			pass

		return blacklist

	# #################################################################################################

	def save_blacklist(self, blacklist):
		with open('/etc/enigma2/blacklist', 'w') as f:
			f.write('\n'.join(blacklist))
			if len(blacklist) > 0:
				f.write('\n')

		try:
			parentalControl.open()
		except:
			pass

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
		blacklist = self.load_blacklist(service_ref_uniq)
		blacklist_need_save = False

		with open("/etc/enigma2/" + self.userbouquet_file_name, "w") as f:
			f.write("#NAME %s\n" % self.name)

			for channel in self.get_channels():
				is_adult = channel.get('adult', False)
				if not self.enable_adult and is_adult:
					continue

				if channel.get('is_separator', False):
					f.write("#SERVICE 1:64:0:0:0:0:0:0:0:0::" + channel['name'] + "\n")
					f.write("#DESCRIPTION " + channel['name'] + "\n")
					continue

				channel_name = channel['name']
				url = self.proxy_url + (self.play_url_pattern % self.encode_channel_key(channel['key']))

				if self.user_agent:
					url += '#User-Agent=%s' % self.user_agent

				url = url.replace(':', '%3a')

				service_ref = self.service_ref_get(lamedb, channel_name, player_id, channel['id'])

				if is_adult and service_ref.endswith(service_ref_uniq) and service_ref not in blacklist:
					blacklist.append(service_ref + url)
					blacklist_need_save = True

				f.write("#SERVICE " + service_ref + url + ":" + channel_name + "\n")
				f.write("#DESCRIPTION " + channel_name + "\n")

				if self.enable_picons and service_ref.endswith(service_ref_uniq) and 'picon' in channel:
					picons[ service_ref[:-1].replace(':', '_') ] = channel['picon']

		first_export = True
		with open("/etc/enigma2/bouquets.tv", "r") as f:
			for line in f.readlines():
				if self.userbouquet_file_name in line:
					first_export = False
					break

		if first_export:
			with open("/etc/enigma2/bouquets.tv", "a") as f:
				f.write('#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "' + self.userbouquet_file_name + '" ORDER BY bouquet' + "\n")

		if blacklist_need_save:
			self.save_blacklist(blacklist)

		self.reload_bouquets()

		if self.enable_picons:
			threading.Thread(target=BouquetGeneratorTemplate.download_picons,args=(picons,)).start()

	# #################################################################################################
