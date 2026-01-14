# -*- coding: utf-8 -*-
from tools_xbmc.tools.md5crypt import md5crypt
from tools_archivczsk.contentprovider.exception import AddonErrorException, LoginException
import xml.etree.ElementTree as ET
from hashlib import md5, sha1
import traceback
from datetime import datetime
from time import time, mktime

# #################################################################################################

class ResolveException(Exception):
	pass

class WebshareLoginFail(LoginException):
	pass

class WebshareApiError(AddonErrorException):
	pass

# #################################################################################################

class Webshare():
	BASE_URL = 'https://webshare.cz'

	def __init__(self, content_provider):
		self.cp = content_provider
		self.page_limit = 100
		self.device_id = "123456"
		self.login_data = {}
		self.bg_task_id = None
		self.cleanup_idents = {}
		self.req_session = self.cp.get_requests_session()
		self.load_login_data()

	# #################################################################################################

	def load_login_data(self):
		self.load_login_data = self.cp.load_cached_data('login')
		self.login_data['load_time'] = 0 # this will force reload of user data

	# #################################################################################################

	def save_login_data(self):
		self.cp.save_cached_data('login', self.login_data)

	# #################################################################################################

	@staticmethod
	def get_password_hash(password, salt):
		return sha1(md5crypt(password.encode('utf-8'), salt.encode('utf-8'))).hexdigest()

	# #################################################################################################

	def login(self):
		username = self.cp.get_setting('username')
		password = self.cp.get_setting('password')

		if not username or not password:
			self.cp.log_info("Webshare login data not provided - continuing with free account")
			return False

		try:
			xml = self.call_ws_api('salt', { 'username_or_email':username })

			status = xml.find('status').text
			if status != 'OK':
				raise WebshareLoginFail( xml.find('message').text )

			salt = xml.find('salt').text
			if salt is None:
				salt = ''

			password = self.get_password_hash(password, salt)
			digest = md5(username.encode('utf-8') + b':Webshare:' + password.encode('utf-8')).hexdigest()
			# login
			xml = self.call_ws_api('login', { 'username_or_email':username, 'password':password, 'digest': digest, 'keep_logged_in':1 })

			status = xml.find('status').text
			if status != 'OK':
				raise WebshareLoginFail( xml.find('message').text )

		except WebshareLoginFail as e:
			self.cp.log_error('Webshare login failed:')
			self.cp.log_exception()
			raise

		self.login_data['token'] = xml.find('token').text
		return True

	# #################################################################################################

	def call_ws_api(self, endpoint, data=None):
		if data is None:
			data = {}

		if 'token' in self.login_data:
			data.update({'wst': self.login_data['token']})

		headers = {
			'X-Requested-With':'XMLHttpRequest',
			'Accept':'text/xml; charset=UTF-8',
			'Referer': self.BASE_URL
		}

		url = '{}/api/{}/'.format(self.BASE_URL, endpoint)
		response = self.req_session.post(url, data=data, headers=headers)
#		with open("/tmp/ws_request.txt", "a") as f:
#			f.write("URL: %s\n" % url)
#			f.write("DATA: %s\n" % data)
#			f.write("RESPONSE: %s\n" % response.text)
#			f.write("-----------------------------------\n")

		if response.status_code != 200:
			raise WebshareApiError("Wrong response status code: %d" % response.status_code)

		return ET.fromstring(response.content)

	# #################################################################################################

	def get_expiration(self, subscripted_until ):
		if not subscripted_until:
			return 0

		# 2022-09-14 18:43:29
		try:
			return int(mktime(datetime.strptime(subscripted_until, '%Y-%m-%d %H:%M:%S').timetuple()))
		except OverflowError:
			# temporary workaround for year 2038 problem ...
			subscripted_until = '2037' + subscripted_until[4:]
			return int(mktime(datetime.strptime(subscripted_until, '%Y-%m-%d %H:%M:%S').timetuple()))

	# #################################################################################################

	def get_user_info(self):
		try:
			xml = self.call_ws_api('user_data')
		except Exception as e:
			self.cp.log_error('Webshare get user info failed')
			self.cp.log_exception()
			raise WebshareApiError( str(e) )

		isVip = xml.find('vip').text
		vipDays = xml.find('vip_days').text
		ident = xml.find('ident').text

		status = xml.find('status').text
		if status != 'OK':
			raise WebshareLoginFail( "%s" % status or self.cp._("Failed to get user informations") )

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
			login_checksum = self.cp.get_settings_checksum(('username', 'password',))
			if (self.login_data.get('credentials_ok', True) and 'token' not in self.login_data) or self.login_data.get('checksum', '') != login_checksum:
				# data not loaded from cache - do fresh login
				self.login_data = {}
				if self.login():
					self.login_data["checksum"] = login_checksum

			if 'token' in self.login_data:
				if 'expiration' not in self.login_data or self.login_data.get('load_time', 0) + (3600 * 24) < int(time()):
					self.get_user_info()

				if int(time()) > self.login_data['expiration']:
					self.cp.log_info("Webshare subscription expired")

		except Exception as e:
			if try_nr == 0 and 'token' in self.login_data:
				del self.login_data['token']

				# something failed try once more time with fresh login
				self.refresh_login_data(try_nr+1)
			else:
				self.cp.log_error("Webshare login failed: %s" % str(e))
				self.login_data['credentials_ok'] = False
				self.save_login_data()
				raise

		return self.login_data.get('days_left', -1)

	# #################################################################################################

	def get_file_password_salt(self, ident):
		xml = self.call_ws_api('file_password_salt', {'ident': ident})

		if xml.find('status').text == 'OK':
			return xml.find('salt').text

		return None

	# #################################################################################################

	def check_premium(self):
		if self.login_data.get('checksum') is not None:
			# if there are login data provided, then check valid subscription
			token = self.login_data.get('token')

			if not token:
				self.cp.show_info(self.cp._("Wrong webshare login data provided"), noexit=True)
				return

			if int(time()) > self.login_data.get('expiration', 0):
				self.cp.show_info(self.cp._("Webshare subscription expired. Only very low quality videos will play and seeking forward/backwad will not work at all."), noexit=True)

	# #################################################################################################

	def resolve(self, ident):
		self.refresh_login_data()

		request_data = {
			'ident': ident,
			'download_type': 'video_stream',
			'device_uuid': self.device_id
		}

		salt = self.get_file_password_salt(ident)
		if salt:
			raise AddonErrorException(self.cp._('File is password protected'))

		xml = self.call_ws_api('file_link', request_data)

		if xml.find('status').text != 'OK':
			self.login_data = {}
			raise ResolveException(self.cp._("Failed to resolve file") + ": %s" % xml.find('message').text)

		if self.cp.get_setting('cleanup_history'):
			self.cleanup_idents[ident] = True

			if self.bg_task_id == None:
				self.bg_task_id = self.cp.bgservice.run_in_loop('CleanupWsHistory', 900, self.cleanup_ws_history)

		return xml.find('link').text

	# #################################################################################################

	def cleanup_ws_history(self):
		if not self.cleanup_idents:
			if self.bg_task_id != None:
				# no idents to remove - stop task from being run
				self.cp.bgservice.run_in_loop_stop(self.bg_task_id)
				self.bg_task_id = None

			return

		xml = self.call_ws_api('history', {'offset' : 0, 'limit': len(self.cleanup_idents) + 2})

		for f in xml.findall('file'):
			ident = f.find('ident').text

			if ident in self.cleanup_idents:
				download_id = f.find('download_id').text
				self.cp.log_debug("Removing item with ident %s and download_id %s from webshare history" % (ident, download_id))
				self.call_ws_api('clear_history', {'ids' : download_id})
				del self.cleanup_idents[ident]

	# #################################################################################################

	def convert_size(self, size_bytes):
		# convert to MB
		size = float(size_bytes) / 1024 / 1024

		if size > 1024:
			return "%.2f GB" % (size / 1024)
		else:
			return "%.2f MB" % size

	# #################################################################################################

	def search( self, keyword, category='video', page=0 ):
		self.refresh_login_data()

		post_data = {
			'what': keyword,
			'offset': page * self.page_limit,
			'limit': self.page_limit,
			'category': category,
			'sort': 'rating'
		}
		xml = self.call_ws_api('search', post_data )

		if not xml.find('status').text == 'OK':
			self.cp.log_error('Server returned error status, response: %s' % xml.find('message').text)
			return [], False

		result = []

#		total = int(xml.find('total').text)
		for file in xml.findall('file'):
			if file.find('password').text == '1':
				continue

			result.append({
				'title': file.find('name').text,
				'ident': file.find('ident').text,
				'size': self.convert_size(int(file.find('size').text)),
				'img': file.find('img').text
			})

		return result, int(xml.find('total').text) > ((page*self.page_limit) + len(result))

	# #################################################################################################
