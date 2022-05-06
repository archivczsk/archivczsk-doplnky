# -*- coding: utf-8 -*-
#
# addon by skyjet based on misanov's addon based on waladir plugin :-)
#

import sys, os, string, random, time, json, uuid, requests, re
from datetime import datetime, timedelta 
from datetime import date
import threading, traceback

import base64
from lameDB import lameDB

try:
	from urllib import quote
	
	def py2_encode_utf8( text ):
		return text.encode('utf-8', 'ignore')
	
	def py2_decode_utf8( text ):
		return text.decode('utf-8', 'ignore')

except:
	from urllib.parse import quote

	def py2_encode_utf8( text ):
		return text
	
	def py2_decode_utf8( text ):
		return text

############### init ################

_HEADER_UNITY = {
	"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0",
	"Content-Type":"application/json"
}

_HEADER = {
	"X-NanguTv-App-Version" : "Android#6.4.1",
	"User-Agent" : "Dalvik/2.1.0",
	"Accept-Encoding" : "gzip",
	"Content-Type" : "application/x-www-form-urlencoded;charset=UTF-8",
}

def _log_dummy(message):
	print('[O2TV]: ' + message )
	pass


class O2tv:
	def __init__(self, username, password, deviceid, devicename="tvbox", data_dir=None, log_function=None ):
		self.username = username
		self.password = password
		self.deviceid = deviceid
		self.devicename = devicename
		self.data_dir = data_dir
		self.log_function = log_function if log_function else _log_dummy
		self.devices = None
		self.access_token = None
		self.access_token_life = 0
		self.sdata = None
		self.tariff = None
		self.header_unity = _HEADER_UNITY
		self.header = _HEADER
		self.header["X-NanguTv-Device-Id"] = self.deviceid
		self.header["X-NanguTv-Device-Name"] = self.devicename
		self.channels = {}

		if self.data_dir:
			try:
				# load access token
				with open(os.path.join(self.data_dir, 'login.json'), "r") as file:
					login_data = json.load(file)
					self.access_token = login_data['token']
					self.access_token_life = login_data['expires']
					
					self.header_unity["x-o2tv-access-token"] = self.access_token
					self.header["X-NanguTv-Access-Token"] = self.access_token

					self.log_function("Login data loaded from cache")
			except:
				pass

	# #################################################################################################
	
	def save_access_token(self):
		if self.data_dir and self.access_token:
			with open( os.path.join(self.data_dir, 'login.json'), "w") as file:
				login_data = {
					'token': self.access_token,
					'expires': self.access_token_life
				}
				json.dump( login_data, file )

	# #################################################################################################
	
	def showError(self, msg):
		self.log_function("O2TV API ERROR: %s" % msg )
		raise Exception(msg)

	# #################################################################################################

	def call_o2_api(self, url, data=None, params=None, header=None):
		err_msg = None
		
		try:
			if data:
				resp = requests.post( url, data=data, headers=header )
			else:
				resp = requests.get( url, params=data, headers=header )
			
#			self.log_function( "URL: %s (%s)" % (url, data or params or "none") )
#			self.log_function( "RESPONSE: %s" % resp.text )
			
			if resp.status_code == 200:
				try:
					return resp.json()
				except:
					return {}
			else:
				err_msg = "Neočekávaný návratový kód ze serveru: %d" % resp.status_code
		except Exception as e:
			err_msg = str(e)
		
		if err_msg:
			self.log_function( "O2API error for URL %s: %s" % (url, traceback.format_exc()))
			self.showError( "O2TVAPI: %s" % err_msg )

	# #################################################################################################

	def get_access_token(self):
		if '@' in self.username:
			post = { "username" : self.username, "password" : self.password }
			data = self.call_o2_api(url = "https://ottmediator.o2tv.cz:4443/ottmediator-war/login", data=post, header=self.header)
		
			if "services" in data and "remote_access_token" in data and len(data["remote_access_token"]) > 0 and "service_id" in data["services"][0] and len(data["services"][0]["service_id"]) > 0:
				remote_access_token = data["remote_access_token"]
				service_id = data["services"][0]['service_id']
		
				post = {"service_id" : service_id, "remote_access_token" : remote_access_token}
				data = self.call_o2_api(url = "https://ottmediator.o2tv.cz:4443/ottmediator-war/loginChoiceService", data=post, header = self.header)
		
				post = {
					"grant_type" : "remote_access_token",
					"client_id" : "tef-web-portal-etnetera",
					"client_secret" : "2b16ac9984cd60dd0154f779ef200679",
					"platform_id" : "231a7d6678d00c65f6f3b2aaa699a0d0",
					"language" : "cs",
					"remote_access_token" : str(remote_access_token),
					"authority" : "tef-sso",
					"isp_id" : "1"
				}
				
				data = self.call_o2_api(url = "https://oauth.o2tv.cz/oauth/token", data=post, header=self.header)

				self.access_token = data["access_token"]
				self.access_token_life = (int(time.time()) +  int(data["expires_in"] / 1000)) - 3600
		else:
			post = {
				"grant_type" : "password",
				"client_id" : "tef-web-portal-etnetera",
				"client_secret" : "2b16ac9984cd60dd0154f779ef200679",
				"platform_id" : "231a7d6678d00c65f6f3b2aaa699a0d0",
				"language" : "cs",
				"username" : self.username,
				"password" : self.password
			}
			
			data = self.call_o2_api(url = "https://oauth.o2tv.cz/oauth/token", data=post, header=self.header)
			
			self.access_token = data["access_token"]
			self.access_token_life = (int(time.time()) +  int(data["expires_in"] / 1000)) - 3600

		self.save_access_token()
		self.log_function('Token OK')

	# #################################################################################################
	
	def refresh_configuration(self, force_refresh=False, iter=0):
		err_msg = None
		try:
			if not self.access_token or self.access_token_life < int(time.time()):
				self.get_access_token()
				self.header_unity["x-o2tv-access-token"] = self.access_token
				self.header["X-NanguTv-Access-Token"] = self.access_token
				
			if not self.tariff or force_refresh:
				try:
					data = self.call_o2_api(url = "https://app.o2tv.cz/sws/subscription/settings/subscription-configuration.json", header=self.header)
				except Exception as e:
					err_msg = str(e)
					
				if err_msg:
					if iter == 0:
							# something failed - try once more with new access toknen
							self.access_token = None
							self.refresh_configuration(force_refresh, iter + 1)
					else:
						raise Exception( err_msg )
					
				if "isp" in data and len(data["isp"]) > 0 and "locality" in data and len(data["locality"]) > 0 and "billingParams" in data and len(data["billingParams"]) > 0 and "offers" in data["billingParams"] and len(data["billingParams"]["offers"]) > 0 and "tariff" in data["billingParams"] and len(data["billingParams"]["tariff"]) > 0:
					self.subscription = data["subscription"]
					self.isp = data["isp"]
					self.locality = data["locality"]
					self.offers = data["billingParams"]["offers"]
					self.tariff = data["billingParams"]["tariff"]
					self.devices = data["pairedDevices"]
				else:
					raise Exception( "Získávaní konfigurace selhalo" )
				
		except Exception as e:
			err_msg = str(e)
			
		if err_msg:
			self.showError( "Přihlášení selhalo: %s" % err_msg )

	# #################################################################################################
	
	def device_remove(self,did):
		self.refresh_configuration()
		if did:
			post = {"deviceId": did}
			self.call_o2_api('https://app.o2tv.cz/sws/subscription/settings/remove-device.json', data=post, header=self.header )

	# #################################################################################################
	
	def search(self, query ):
		self.refresh_configuration()
		
		max_ts = int(time.mktime(datetime.now().timetuple()))
		
		data = self.call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/search/tv/depr/?groupLimit=1&maxEnd=" + str(max_ts*1000) + "&q=" + quote(query), header=self.header_unity)
		
		if "groupedSearch" in data and "groups" in data["groupedSearch"] and len(data["groupedSearch"]["groups"]) > 0:
			return data["groupedSearch"]["groups"]

		return []
	
	# #################################################################################################
	
	def get_channel_epg(self, ch, fromts, tots):
		self.refresh_configuration()

		post = {
			"channelKey": ch,
			"fromTimestamp": fromts,
			"imageSize": "LARGE",
			"language": "ces",
			"offer": self.offers,
			"toTimestamp": tots
		}
		
		try:
			resp = self.call_o2_api('https://app.o2tv.cz/sws/server/tv/channel-programs.json', data=post, header=self.header)
		except:
			resp = []
		
		return resp

	# #################################################################################################
	
	def get_channels(self, refresh_channels_data=False):
		self.refresh_configuration()
		
		if not self.channels:
			channels = {}
			
			post = {
				"locality" : self.locality,
				"tariff" : self.tariff,
				"isp" : self.isp,
				"language" : "ces",
				"deviceType" : "STB",
				"liveTvStreamingProtocol" : "HLS",
				"offer" : self.offers
			}
			data = self.call_o2_api(url = "https://app.o2tv.cz/sws/server/tv/channels.json", data=post, header=self.header)
	
			purchased_channels = data['purchasedChannels']
			
			for channel_key, item in data["channels"].items():
				if channel_key in purchased_channels:
					if item['channelType'] != 'TV':
						continue
					
					channels[ channel_key ] = {
							'key' : channel_key, #item['channelKey'],
							'id' : item['channelId'],
							'number': item['channelNumber'],
							'type': item['channelType'],
							'name': item['channelName'],
							'weight': item['weight'],
							'adult' : 'audience' in item and item['audience'].upper() == 'INDECENT',
							'picon': item['logo'],
							'timeshift': item['timeShiftDuration'] if item['timeShiftEnabled'] else 0,
							'screenshot': item['screenshots'][0],
						}
		
			self.channels = channels
			refresh_channels_data = True
			
		if refresh_channels_data:
			self.update_channels_data()
		return self.channels
	
	# #################################################################################################
	
	def get_channels_sorted(self, refresh_channels_data=False):
		self.get_channels(refresh_channels_data)
		return sorted(list(self.channels.values()), key=lambda _channel: _channel['number'])

	# #################################################################################################
	
	def update_channels_data(self):
		self.refresh_configuration()
		
		data = self.call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/channels/", header=self.header_unity)
		
		if "result" in data and len(data["result"]) > 0:
			for channel in data["result"]:
				try:
					ch = self.channels[ channel["channel"]['channelKey'] ]
				except:
					continue
				
				ch['logo'] = "https://www.o2tv.cz/" + channel["channel"]["images"]["color"]["url"]
				if 'live' in channel: 
					ch['live'] = channel['live']
					ch['live']['start'] = int(ch['live']['start'] / 1000)
					ch['live']['end'] = int(ch['live']['end'] / 1000)
				else:
					ch['live'] = None
	
	# #################################################################################################
	
	def get_epg_detail(self, epg_id ):
		self.refresh_configuration()
		
		epgdata = self.call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/programs/" + str(epg_id) + "/", header=self.header_unity)

		img = None;
		if "images" in epgdata and len(epgdata["images"]) > 0:	
			img = "https://www.o2tv.cz/" + epgdata["images"][0]["cover"]
		else:
			img = None
		
		return {
			'img' : img,
			'name': epgdata.get("name"),
			'long' : epgdata.get("longDescription"),
			'short' : epgdata.get("shortDescription"),
			'start' : int(epgdata['start'] / 1000),
			'end' : int(epgdata['end'] / 1000)
		}
		
	# #################################################################################################
	
	def get_user_channel_lists(self):
		self.refresh_configuration()
		
		data = self.call_o2_api(url = "https://app.o2tv.cz/sws/subscription/settings/get-user-pref.json?name=nangu.channelListUserChannelNumbers", header=self.header)
		
		result = {}
		if "listUserChannelNumbers" in data and len(data["listUserChannelNumbers"]) > 0:
			data = data["listUserChannelNumbers"]
			for list_name in data:
				result[list_name.replace('user::', '')] = list(x[0] for x in sorted(data[list_name].items(), key=lambda x : x[1]))
		
		return result
	
	# #################################################################################################
	
	def get_recordings(self):
		self.refresh_configuration()
		
		header_unity2 = self.header_unity.copy()
		header_unity2["x-o2tv-device-id"] = self.deviceid
		header_unity2["x-o2tv-device-name"] = self.devicename
		
		if not self.sdata:
			data = self.call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/user/profile/", header = header_unity2)
			self.sdata = str(data['sdata'])
		
		header_unity2["x-o2tv-sdata"] = self.sdata
	
		data_pvr = self.call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/recordings/", header = header_unity2)
		
		return data_pvr

	# #################################################################################################
	
	def delete_recording( self, pvrProgramId ):
		self.refresh_configuration()
		
		post = {"pvrProgramId" : int(pvrProgramId)}
		
		try:
			data = self.call_o2_api(url = "https://app.o2tv.cz/sws/subscription/vod/pvr-remove-program.json", data = post, header = self.header)
		except:
			return False
		
		return True

	# #################################################################################################
	
	def add_recording( self, epg_id ):
		self.refresh_configuration()
		
		post = {"epgId" : int(epg_id) }
		try:
			data = self.call_o2_api(url = "https://app.o2tv.cz/sws/subscription/vod/pvr-add-program.json", data = post, header=self.header)
		except:
			return False
		
		return True

	# #################################################################################################
	
	def resolve_streams(self, post ):
		data = self.call_o2_api(url = "https://app.o2tv.cz/sws/server/streaming/uris.json", data=post, header=self.header)
	
		playlist = None
		url = ""
		if "uris" in data and len(data["uris"]) > 0 and "uri" in data["uris"][0] and len(data["uris"][0]["uri"]) > 0 :
			playlist = ""
			for uris in data["uris"]:
				if uris["resolution"] == "HD":
					playlist = uris["uri"]
					break

			if playlist == "":
				playlist = data["uris"][0]["uri"]

		result = []
		if playlist:
			r = requests.get(playlist, headers=_HEADER).text
			for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+)\s(?P<chunklist>[^\s]+)', r, re.DOTALL):
				bandwidth = int(m.group('bandwidth'))
				quality = ""
				if bandwidth < 1400000:
					quality = "180p"
				elif bandwidth < 2450000:
					quality = "360p"
				elif bandwidth < 4100000:
					quality = "480p"
				elif bandwidth < 6000000:
					quality = "720p"
				else:
					quality = "1080p"
				url = m.group('chunklist')
				result.append( {"url": url, "quality": quality, 'bandwidth': bandwidth } )
			
			result = sorted( result, key=lambda r: r['bandwidth'], reverse=True )
		return result
	
	# #################################################################################################
	
	def get_video_link(self, channel_key, start, end, epg_id ):
		self.refresh_configuration()
		
		post = {
			"serviceType" : "TIMESHIFT_TV",
			"deviceType" : "STB",
			"streamingProtocol" : "HLS",
			"subscriptionCode" : self.subscription,
			"channelKey" : channel_key,
			"fromTimestamp" : start,
			"toTimestamp" : end,
			"id" : epg_id,
			"encryptionType" : "NONE"
		}
		
		return self.resolve_streams(post)
	
	# #################################################################################################
	
	def get_live_link(self, channel_key ):
		self.refresh_configuration()
		
		post = {
			"serviceType" : "LIVE_TV",
			"deviceType" : "STB",
			"streamingProtocol" : "HLS",
			"subscriptionCode" : self.subscription,
			"channelKey" : channel_key,
			"encryptionType" : "NONE"
		}

		return self.resolve_streams(post)

	# #################################################################################################

	def get_recording_link(self, pvrProgramId):
		self.refresh_configuration()
		
		post = {
			"serviceType" : "NPVR",
			"deviceType" : "STB",
			"streamingProtocol" : "HLS",
			"subscriptionCode" : self.subscription,
			"contentId" : pvrProgramId,
			"encryptionType" : "NONE"
		}
		
		return self.resolve_streams(post)

	# #################################################################################################
	

class O2tvBouquetGenerator:
	def __init__(self):
		# configuration to make this class little bit reusable also in other addons
		self.proxy_url = "http://127.0.0.1:18082"
		self.PROXY_VER='1'
		self.prefix = "o2tv"
		self.name = "O2TV"
		self.sid_start = 0xE000
		self.tid = 5
		self.onid = 2
		self.namespace = 0xE030000
	
	def flush_enigma2_settings(self):
		try:
			from Components.config import configfile
			
			configfile.save()
			
			# reload configuration in antiktv_proxy
			requests.get( self.proxy_url + '/reloadconfig' )
		except:
			pass

	# bouquet generator funcions based on AntikTV addon
	@staticmethod
	def download_picons(picons):
		if not os.path.exists( '/usr/share/enigma2/picon' ):
			os.mkdir('/usr/share/enigma2/picon')
			
		for ref in picons:
			if not picons[ref].endswith('.png'):
				continue
			
			fileout = '/usr/share/enigma2/picon/' + ref + '.png'
			
			if not os.path.exists(fileout):
				try:
					r = requests.get( picons[ref].replace('https://', 'http://').replace('64x64','220x220'), timeout=3 )
					if r.status_code == 200:
						with open(fileout, 'wb') as f:
							f.write( r.content )
				except:
					pass
	
	def build_service_ref( self, service, player_id ):
		return player_id + ":0:{:X}:{:X}:{:X}:{:X}:{:X}:0:0:0:".format( service.ServiceType, service.ServiceID, service.Transponder.TransportStreamID, service.Transponder.OriginalNetworkID, service.Transponder.DVBNameSpace )


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
	
	
	def generate_bouquet(self, channels, enable_adult=True, enable_xmlepg=False, enable_picons=False, player_name="0"):
		# if epg generator is disabled, then try to create service references based on lamedb
		if enable_xmlepg:
			lamedb = None
		else:
			lamedb = lameDB("/etc/enigma2/lamedb")
		
		if player_name == "1": # gstplayer
			player_id = "5001"
		elif player_name == "2": # exteplayer3
			player_id = "5002"
		elif player_name == "3": # DMM
			player_id = "8193"
		elif player_name == "4": # DVB service (OE >=2.5)
			player_id = "1"
		else:
			player_id = "4097" # system default
	
		file_name = "userbouquet.%s.tv" % self.prefix
		
		picons = {}
		
		service_ref_uniq = ':%X:%X:%X:0:0:0:' % (self.tid, self.onid, self.namespace)
		
		with open( "/etc/enigma2/" + file_name, "w" ) as f:
			f.write( "#NAME %s TV\n" % self.name )
			
			for channel in channels:
				if not enable_adult and channel['adult']:
					continue
				
				channel_name = channel['name']
				url = self.proxy_url + '/playlive/' + base64.b64encode( channel['key'].encode('utf-8') ).decode('utf-8')
				url = quote( url )
				
				service_ref = self.service_ref_get( lamedb, channel_name, player_id, channel['id'] )
					
				f.write( "#SERVICE " + service_ref + url + ":" + channel_name + "\n")
				f.write( "#DESCRIPTION " + channel_name + "\n")
				
				try:
					if enable_picons and service_ref.endswith( service_ref_uniq ):
						picons[ service_ref[:-1].replace(':', '_') ] = channel['picon']
				except:
					pass
		
		first_export = True
		with open( "/etc/enigma2/bouquets.tv", "r" ) as f:
			for line in f.readlines():
				if file_name in line:
					first_export = False
					break
		
		if first_export:
			with open( "/etc/enigma2/bouquets.tv", "a" ) as f:
				f.write( '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "' + file_name + '" ORDER BY bouquet' + "\n" )
	
		try:
			requests.get("http://127.0.0.1/web/servicelistreload?mode=2")
		except:
			pass
		
		if enable_picons:
			threading.Thread(target=O2tvBouquetGenerator.download_picons,args=(picons,)).start()
		
		
		return "%s userbouquet vygenerovaný" % self.name
	
	
	def install_proxy(self):
		src_file = os.path.dirname(__file__) + '/' + self.prefix + '_proxy.sh'
		
		for i in range(3):
			try:
				response = requests.get( self.proxy_url + '/info', timeout=2 )
				
				if response.text.startswith( self.prefix + "_proxy"):
					if response.text == self.prefix + "_proxy" + self.PROXY_VER:
						# current running version match
						return True
					else:
						os.chmod( src_file, 0o755 )
						self.flush_enigma2_settings()
						
						# wrong runnig version - restart it and try again
						os.system('/etc/init.d/%s_proxy.sh stop' % self.prefix )
						time.sleep(2)
						os.system('/etc/init.d/%s_proxy.sh start' % self.prefix )
						time.sleep(2)
				else:
					# incorrect response - install new proxy
					break
			except:
				# something's wrong - we will try again
				pass
		
		os.chmod( src_file, 0o755 )
		self.flush_enigma2_settings()
		try:
			os.symlink( src_file, '/etc/init.d/%s_proxy.sh' % self.prefix )
		except:
			pass
		
		try:
			os.system('update-rc.d %s_proxy.sh defaults' % self.prefix )
			os.system('/etc/init.d/%s_proxy.sh start' % self.prefix )
			time.sleep(1)
		except:
			pass
	
		for i in range(5):
			try:
				response = requests.get( self.proxy_url + '/info', timeout=1 )
			except:
				response = None
				time.sleep(1)
				pass
			
			if response != None and response.text == self.prefix + "_proxy" + self.PROXY_VER:
				return True
		
		return False
