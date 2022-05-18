import os
from md5crypt import md5crypt
import xml.etree.ElementTree as ET
from hashlib import md5, sha1
import traceback
import requests
from datetime import datetime
from time import time, mktime
import json

# #################################################################################################

class ResolveException(Exception):
	pass

class WebshareLoginFail(Exception):
	pass

class WebshareApiError(Exception):
	pass

class WebshareNoSubsctiption(Exception):
	pass

BASE = 'https://webshare.cz'

# #################################################################################################

def _log_dummy(message):
	print('[Webshare]: ' + message )
	pass

# #################################################################################################

class Webshare():
	def __init__(self, username=None, password=None, device_id="123456", data_dir=None, log_function=None):
		self.username = username
		self.password = password
		self.data_dir = data_dir
		self.device_id = device_id
		self.log_function = log_function if log_function else _log_dummy
		self.login_data = {}
		self.load_login_data()
		
	# #################################################################################################
	
	def load_login_data(self):
		if self.data_dir:
			try:
				# load access token
				with open(os.path.join(self.data_dir, 'webshare_login.json'), "r") as f:
					self.login_data = json.load(f)
					self.login_data['load_time'] = 0 # this will force reload of user data
					self.log_function("Webshare login data loaded from cache")
			except:
				pass

	# #################################################################################################
	
	def save_login_data(self):
		if self.data_dir:
				with open(os.path.join(self.data_dir, 'webshare_login.json' ), "w") as f:
					json.dump(self.login_data, f )

	# #################################################################################################
	
	def login(self):
		if not self.username or len(self.username) == 0 or not self.password or len(self.password) == 0:
			 self.log_function( "Nezadané prihlasovacie údaje pre Webshare - pokračujem s free účtom" )
			 raise WebshareNoSubsctiption( "Nezadané prihlasovacie údaje pre Webshare - pokračujem s free účtom" )
		
		try:
#			self.log_function("Trying to get salt")
			data = self.call_ws_api('/api/salt/', { 'username_or_email':self.username } )
			
			xml = ET.fromstring(data)
			status = xml.find('status').text
			if status != 'OK':
				raise WebshareLoginFail( "Wrong response to salt command: %s" % xml.find('message').text )
			
			salt = xml.find('salt').text
			if salt is None:
				salt = ''

			password = sha1(md5crypt(self.password.encode('utf-8'), salt.encode('utf-8'))).hexdigest()
			digest = md5(self.username.encode('utf-8') + b':Webshare:' + self.password.encode('utf-8')).hexdigest()
			# login
			data = self.call_ws_api('/api/login/', { 'username_or_email':self.username, 'password':password, 'digest': digest, 'keep_logged_in':1 } )

			xml = ET.fromstring(data)

			status = xml.find('status').text
			if status != 'OK':
				raise WebshareLoginFail( "Wrong response to login command: %s" % xml.find('message').text )

		except Exception as e:
			self.log_function('Webshare err login: {}'.format(traceback.format_exc()))
			raise WebshareLoginFail( str(e) )


		self.login_data['token'] = xml.find('token').text
		
	# #################################################################################################
	
	def call_ws_api(self, endpoint, data=None):
		if data is None:
			data = {}
			
		if 'token' in self.login_data:
			data.update({'wst': self.login_data['token']})

		headers = {
			'X-Requested-With':'XMLHttpRequest',
			'Accept':'text/xml; charset=UTF-8',
			'Referer': BASE
		}
		
		response = requests.post(BASE + endpoint, data=data, headers=headers )
#		with open( "/tmp/ws_request.txt", "a" ) as f:
#			f.write( "URL: %s\n" % (BASE + endpoint) )
#			f.write( "DATA: %s\n" % data )
#			f.write( "RESPONSE: %s\n" % response.text )
#			f.write( "-----------------------------------\n" )
		
		if response.status_code != 200:
			raise WebshareApiError("Wrong response status code: %d" % response.status_code)
			
		return response.text

	# #################################################################################################

	def get_chsum(self):
		if not self.username or not self.password or len(self.username) == 0 or len( self.password) == 0:
			return None
		
		return md5(
			"{}|{}".format(self.password.encode('utf-8'),
						   self.username.encode('utf-8')).encode('utf-8')).hexdigest()

	# #################################################################################################

	def get_expiration(self, subscripted_until ):
		if not subscripted_until:
			return 0
		
		# 2022-09-14 18:43:29
		return int(mktime(datetime.strptime(subscripted_until, '%Y-%m-%d %H:%M:%S').timetuple()))

	# #################################################################################################

	def get_user_info(self):
		try:
			data = self.call_ws_api('/api/user_data/')
		except Exception as e:
			self.log_function('Webshare get user info fail: {}'.format(traceback.format_exc()))
			raise WebshareApiError( str(e) )

		xml = ET.fromstring(data)
		isVip = xml.find('vip').text
		vipDays = xml.find('vip_days').text
		ident = xml.find('ident').text

		status = xml.find('status').text
		if status != 'OK':
			raise WebshareLoginFail( "%s" % status or "Nepodarilo sa získať informácie o užívateľovi" )

		vip_days = xml.find('vip_days').text
		if not vip_days:
			vip_days = -1

		subscripted_until = xml.find('vip_until').text
		if not subscripted_until:
			subscripted_until = "1990-01-01 00:00:00"
		
		self.login_data['load_time'] = int(time())
		self.login_data['days_left'] = int( vip_days )
		self.login_data['expiration'] = self.get_expiration( subscripted_until )
		self.save_login_data()

	# #################################################################################################

	def refresh_login_data(self, try_nr=0):
		try:
			login_checksum = self.get_chsum()
			if len(self.login_data) == 0 or self.login_data.get('checksum','') != login_checksum:
				# data not loaded from cache - do fresh login
				self.login_data = { "checksum": login_checksum }
				self.login()
				
			if 'token' in self.login_data:
				if not 'expiration' in self.login_data or self.login_data.get('load_time', 0) + (3600*24) < int(time()):
					self.get_user_info()
				
				if int(time()) > self.login_data['expiration']:
					self.log_function("Platnosť WebShare predplatného vypršala")

		except Exception as e:
			if try_nr == 0 and 'token' in self.login_data:
				del self.login_data['token']
			
				# something failed try once more time with fresh login
				self.refresh_login_data(try_nr+1)
			else:
				self.log_function( "Webshare login failed: %s" % str(e) )
				self.save_login_data()
		
		return self.login_data.get('days_left', -1)
	
	# #################################################################################################
	
	def resolve(self, ident, dwnType='video_stream'):
		self.refresh_login_data()
		
		if self.login_data.get('checksum') is not None:
			# if there are login data provided, then check valid subscription
			token = self.login_data.get('token')
	
			if not token:
				raise WebshareLoginFail("Neplatné prihlasovacie údaje")
			
			if int(time()) > self.login_data.get('expiration', 0):
				raise WebshareLoginFail("Platnosť predplatného vypršala")

		data = self.call_ws_api('/api/file_link/', {'ident':ident, 'download_type': dwnType, 'device_uuid': self.device_id } )

		xml = ET.fromstring(data)

		if xml.find('status').text != 'OK':
			self.login_data = {}
			raise ResolveException("Nepodarilo sa resolvnúť súbor: %s" % xml.find('message').text )

		return xml.find('link').text
		
	# #################################################################################################
	
	def search( self, title ):
		self.refresh_login_data()
		
		data = self.call_ws_api('/api/search/', {'what': title, 'offset': 0, 'limit': 30, 'category': 'video', 'sort': 'rating' } )

		xml = ET.fromstring(data)
		if not xml.find('status').text == 'OK':
			self.log_funtion('Server returned error status, response: %s' % xml.find('message').text)
			return []
		
		result = []
		
		total = int(xml.find('total').text)
		for file in xml.findall('file'):
			item = {}
			item['title'] = file.find('name').text
			item['url'] = file.find('ident').text
			osize = file.find('size').text
			size = int(file.find('size').text)
			item['size'] = '%d MB' % (int(size)/1024/1024)
			item['img'] = file.find('img').text
			result.append(item)

		return result
	
	# #################################################################################################
