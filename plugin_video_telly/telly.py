# -*- coding: utf-8 -*-
import re, os, datetime, json, requests, traceback
from time import time
import uuid
from tools_archivczsk.contentprovider.exception import LoginException

try:
	from urlparse import urlparse, urlunparse, parse_qsl

except:
	from urllib.parse import urlparse, urlunparse, parse_qsl

_COMMON_HEADERS = {
	'Accept': 'application/json, text/plain, */*',
	'Origin': 'https://stb.tv.itself.cz',
	'Accept-Language': 'ces',
	'User-Agent': 'Mozilla/5.0 (Linux; U; Android 2.0; en-us; Droid Build/ESD20) AppleWebKit/530.17 (KHTML, like Gecko) Version/4.0 Mobile Safari/530.17',
	'Content-Type': 'application/json;charset=UTF-8',
	'Referer': 'https://stb.tv.itself.cz/index-android.html?brand=telly',
	'Accept-Encoding': 'gzip, deflate',
	'X-Requested-With': 'tv.fournetwork.android.box.digi',
}

# #################################################################################################

class TellyChannel:
	def __init__(self, channel_info):
		self.id = channel_info['id']
		self.epg_id = channel_info['id_epg']
		self.name = channel_info['name']
		self.type = channel_info['type']
		self.pvr = channel_info['pvr']
		self.timeshift = int(channel_info['catchup_length']) if channel_info.get('catchup_length') else 0
		self.adult = channel_info['parental_lock'].get('enabled', False)
		self.picon = None
		self.preview = None
		
		# get only first adaptive stream url
		for cs in channel_info['content_sources']:
			self.stream_url = cs.get('stream_profile_urls', {}).get('adaptive')
			if self.stream_url:
				break

	
	# #################################################################################################
	
	def set_picon(self, logo_url):
		if logo_url:
			self.picon = logo_url.replace('{channel_id}', str(self.id))

	# #################################################################################################

	def set_preview(self, preview_url):
		if preview_url:
			self.preview = preview_url.replace('{channel_id}', str(self.id)).replace('{width}','200')

# #################################################################################################

def _log_dummy(message):
	print('[TELLY]: ' + message )
	pass

# #################################################################################################

__debug_nr = 1
def writeDebugRequest(url, params, data, response):
	global __debug_nr

	name = "/tmp/%03d_request_%s" % (__debug_nr, url[8:].replace('/', '_'))

	with open(name, "w") as f:
		f.write(json.dumps({'params': params, 'data': data }))

	name = "/tmp/%03d_response_%s" % (__debug_nr, url[8:].replace('/', '_'))

	with open(name, "w") as f:
		f.write(json.dumps(response))

	__debug_nr += 1

# #################################################################################################


class Telly:

	def __init__(self, data_dir=None, log_function=None ):
		self.device_token = None
		self.log_function = log_function if log_function else _log_dummy
		self.settings = None
		self.data_dir = data_dir
		self.epg_cache = {}
		self.cache_need_save = False
		self.cache_mtime = 0

		if self.data_dir:
			try:
				# load access token
				with open(self.data_dir + '/login.json', "r") as f:
					login_data = json.load(f)
					self.device_token = login_data['token']
					
					self.log_function("Login data loaded from cache")
			except:
				pass
			
	# #################################################################################################

	def save_login_data(self):
		if self.data_dir:
			try:
				if self.device_token:
					# save access token
					with open(self.data_dir + '/login.json', "w") as f:
						json.dump( {'token': self.device_token }, f )
				else:
					os.remove(self.data_dir + '/login.json')
			except:
				pass
	# #################################################################################################
	
	def load_epg_cache(self):
		try:
			try:
				cache_file_mtime = int(os.path.getmtime(self.data_dir + '/epg_cache.json'))
			except:
				cache_file_mtime = 0
			
			if cache_file_mtime > self.cache_mtime:
				with open(self.data_dir + '/epg_cache.json', "r") as file:
					self.epg_cache = json.load(file)
					self.log_function("EPG loaded from cache")
				
				self.cache_mtime = cache_file_mtime
				self.cache_need_save = False
		except:
			pass
		
		return True if self.cache_mtime else False
	
	# #################################################################################################
	
	def save_epg_cache(self):
		if self.data_dir and self.cache_need_save:
			with open(self.data_dir + '/epg_cache.json', 'w') as f:
				json.dump( self.epg_cache, f)
				self.log_function("EPG saved to cache")
				self.cache_need_save = False
				
	# #################################################################################################
	
	def call_telly_api(self, endpoint, data=None, params=None ):
		err_msg = None
		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = "https://backoffice0-vip.tv.itself.cz/" + endpoint
		
		try:
#			self.log_function( "URL: %s (%s)" % (url, data or params or "none") )
#			self.log_function( "DATA: %s" % json.dumps(data) )
			if data:
				resp = requests.post( url, data=json.dumps(data, separators=(',', ':')), headers=_COMMON_HEADERS )
			else:
				resp = requests.get( url, params=params, headers=_COMMON_HEADERS )
			
#			self.log_function( "RESPONSE (%d): %s" % (resp.status_code, resp.text) )
			
			if resp.status_code == 200:
				try:
#					writeDebugRequest(url, data, params, resp.json())
					return resp.json()
				except:
					return {}
			else:
				err_msg = "Neočekávaný návratový kód zo servera: %d" % resp.status_code
		except Exception as e:
			self.log_function("TELLY ERROR:\n"+traceback.format_exc())
			err_msg = str(e)
		
		if err_msg:
			self.log_function( "Telly error for URL %s: %s" % (url, traceback.format_exc()))
			self.log_function( "Telly: %s" % err_msg )
#			self.showError( "Telly: %s" % err_msg )

		return None
	
	# #################################################################################################
	
	def token_is_valid(self):
		if not self.device_token:
			return False

		ret = self.call_telly_api('api/device/checkDeviceTokenValidity/', data = { 'device_token': self.device_token })
		if ret and ret.get('success') and ret.get('subscriber_active') and ret.get('valid'):
			return True
		
		self.device_token = None
		self.save_login_data()
		self.log_function("Telly device token is invalid: %s" % str(ret))
		return False

	# #################################################################################################

	def check_token(self):
		if not self.token_is_valid():
			raise LoginException("Prihlasovací token je neplatný - spárujte zariadenie znova")

	# #################################################################################################

	def get_device_token_by_code(self, code):
		# pair device
		ret = self.call_telly_api('api/device/pairDeviceByPairingCode/', data = { 'pairing_code': str(code), 'brand_code': 'telly'})
		if ret and ret.get('success') and ret.get('token'):
			self.device_token = ret['token']
		else:
			self.log_function("Failed to pair device by pairing code: %s" % str(ret))
			return False
		
		# complete device pairing
		data = {
			'device_token': self.device_token,
			'device_type_code': 'ANDROIDTV',
			'model': 'Samsung',
			'serial_number': str( uuid.uuid1() ),
			'mac_address': ''
		}
		ret = self.call_telly_api('api/device/completeDevicePairing/', data=data )
		if ret and ret.get('success'):
			self.save_login_data()
			return True
		
		self.log_function("Failed to complete device pairing: %s" % str(ret))
		return False
		
	# #################################################################################################
	
	def refresh_settings(self):
		if self.settings:
			return True
		
		ret = self.call_telly_api('api/device/getSettings/', data = { 'device_token': self.device_token })
		if not ret or not ret.get('success'):
			self.check_token()
			return False
		
		s = ret.get('settings',{})
		self.settings = {
			'channel_logo_url': s.get('channel_logo_source_url','') + s.get('channel_logo_url_suffix_template',''),
			'channel_preview_url' : s.get('stream_thumbnailer_url','') + s.get('stream_thumbnailer_url_latest_suffix_template',''),
			'timezone_offset': s.get('timezone_offset', 1) * 60
		}
	
	
	# #################################################################################################

	def get_channel_list(self):
		if not self.device_token:
			return None
		
		self.refresh_settings()

		ret = self.call_telly_api('api/device/getSources/', data={ 'device_token': self.device_token })
		if not ret or not ret.get('success'):
			self.check_token()
			return None

		channels = []
		for ch in ret.get('channels', []):
			channel = TellyChannel(ch)
			channel.set_picon(self.settings['channel_logo_url'])
			channel.set_preview(self.settings['channel_preview_url'])
			channels.append(channel)
		
		return channels

	# #################################################################################################
	
	def get_channels_epg(self, epg_ids, fromts, tots ):
		if not self.device_token:
			return None
		
		data = {
			'lng_priority': [ 'ces' ],
			'from': fromts,
			'to': tots,
			'ids_epg': epg_ids,
			'timezone_offset': self.settings['timezone_offset']
		}
		
		ret = self.call_telly_api( 'https://epg.tv.itself.cz/v2/epg', data=data )
		
		if ret.get('error', True) == True:
			self.check_token()
			return None
		
		return ret.get('broadcasts')
		
	# #################################################################################################
	
	def fill_epg_cache(self, epg_ids, cache_hours=0, epg_data=None ):
		if not self.device_token or cache_hours == 0:
			return

		fromts = int(time())
		tots = (int(time()) + (cache_hours * 3600) + 60)

		if not epg_data:
			if self.cache_mtime and self.cache_mtime < tots - 3600:
				# no need to refill epg cache
				return
			
			epg_data = self.get_channels_epg( epg_ids, fromts, tots )
		
		if not epg_data:
			self.log_function("Failed to get EPG for channels from Telly server")
			return
		
		for epg_id in epg_ids:
			if str(epg_id) not in epg_data:
				continue
			
			ch_epg = []
	
			for one in epg_data[str(epg_id)]:
				if one["name"].startswith('Vysílání od: '):
					continue
				
				ch_epg.append({
					"start": one["timestamp_start"],
					"end": one["timestamp_end"],
					"title": one["name"],
					"desc": one["description_broadcast"] if one["description_broadcast"] else "",
					'img': one.get("poster", {}).get('url', "").replace('{size}', 'stb-new-carousel'),
					'year': one.get('year'),
					'rating': float(one['rating']) / 10 if one.get('rating') else None
				})
				
				if one["timestamp_start"] > tots:
					break
				
			self.epg_cache[str(epg_id)] = ch_epg
			
		self.cache_need_save = True
		
	# #################################################################################################

	def get_channel_current_epg(self, epg_id):
		fromts = int(time())
		title = ""
		del_count = 0
		
		epg_id = str(epg_id)
		if epg_id in self.epg_cache:
			for epg in self.epg_cache[epg_id]:
				if epg["end"] < fromts:
					# cleanup old events
					del_count += 1
				
				if epg["start"] < fromts and epg["end"] > fromts:
					title = epg["title"]
					break
		
		if del_count:
			# save some memory - remove old events from cache
			del self.epg_cache[epg_id][:del_count]
			self.log_function("Deleted %d old events from EPG cache for channell %s" % (del_count, epg_id))
			
		if title == "":
			return None
		
		return epg

	# #################################################################################################

	def get_archiv_channel_programs(self, epg_id, fromts, tots):
		if not self.device_token:
			return
		
		epg_data = self.get_channels_epg( [int(epg_id)], fromts, tots)
		
		for program in epg_data.get(str(epg_id), []):
			if int(time()) > program["timestamp_start"]:
				yield {
					'title': program["name"],
					'start': program["timestamp_start"],
					'end': program["timestamp_end"],
					'img': program.get("poster", {}).get('url', "").replace('{size}', 'stb-new-carousel'),
					'desc': program["description_broadcast"],
					'year': program.get('year'),
					'rating': float(program['rating']) / 10 if program.get('rating') else None
				}
	
	# #################################################################################################
	
	def get_video_link(self, url, enable_h265=False, max_bitrate=None, force_http=False):
		# extract params from url, to set our own request profiles
		u = urlparse( url )
		params = dict(parse_qsl( u.query ))
		url = urlunparse( (u.scheme, u.netloc, u.path, '', '', '') )
		
		if enable_h265:
			profiles_h265 = [
				'profile40', # H265 profil 4K 2160
				'profile41', # H265 profil 4K 1080p
				'profile31', # H265 profil 1080p50
				'profile32', # H265 profil 1080
				'profile34', # H265 profil 720
			]
			
			# prepend h265 profiles
			params['stream_profiles'] = ','.join(profiles_h265) + ',' + params['stream_profiles']
		
		# get master playlist
		resp = requests.get( url, params=params, headers={'User-Agent': 'tv.fournetwork.android.box.digi/2.0.9 (Linux;Android 6.0) ExoPlayerLib/2.11.7'} )
	
		if resp.status_code != 200:
			return []

		if max_bitrate == None:
			max_bitrate = 100000
		elif ' Mbit' in max_bitrate:
			max_bitrate = int(max_bitrate.split(' ')[0]) * 1000
		else:
			max_bitrate = 100000

		video_urls = []
		for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+),RESOLUTION=(?P<resolution>[\dx]+)\s(?P<chunklist>[^\s]+)', resp.text, re.DOTALL):
			bandwidth = int(m.group('bandwidth')) // 1000

			if bandwidth > max_bitrate:
				continue

			video_url = m.group('chunklist')
			if force_http:
				video_url = video_url.replace('https://', 'http://')

			video_codec = 'h265' if '=profile3' in video_url or '=profile4' in video_url else 'h264'
			quality = m.group('resolution').split('x')[1] + 'p ' + video_codec
			
			video_urls.append( { 'url': video_url, 'quality': quality, 'bitrate': bandwidth })
		
		return sorted(video_urls, key=lambda u: u['bitrate'], reverse=True)
			
	# #################################################################################################
	
	def get_archive_video_link(self, ch, fromts, tots, enable_h265=False, max_bitrate=None, force_http=False):
		if not self.device_token:
			return None
		
		params = {
			'device_token': self.device_token,
			'channel_id': ch,
			'start': fromts,
			'end': tots
		}
		
		ret = self.call_telly_api( 'contentd/api/device/getContent', params=params)
		
		if not ret or ret.get('success') != True:
			self.check_token()
			return None
		
		return self.get_video_link(ret['stream_uri'], enable_h265, max_bitrate, force_http)

# #################################################################################################
