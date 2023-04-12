# -*- coding: utf-8 -*-

import os
import json
import traceback
import requests
from datetime import datetime
from time import time, mktime

BASE = 'https://api.kra.sk'

# #################################################################################################

class KraskaResolveException(Exception):
	pass

class KraskaLoginFail(Exception):
	pass

class KraskaApiError(Exception):
	pass

class KraskaNoSubsctiption(Exception):
	pass


# #################################################################################################

class Kraska:
	def __init__(self, content_provider):
		self.cp = content_provider
		self.data_dir = content_provider.data_dir

		self.login_data = {}
		self.load_login_data()
		
	# #################################################################################################
	
	def load_login_data(self):
		if self.data_dir:
			try:
				# load access token
				with open(os.path.join(self.data_dir, 'kraska_login.json'), "r") as f:
					self.login_data = json.load(f)
					self.login_data['load_time'] = 0 # this will force reload of user data
					self.cp.log_debug("Kraska login data loaded from cache")
			except:
				pass

	# #################################################################################################
	
	def save_login_data(self):
		if self.data_dir:
			with open(os.path.join(self.data_dir, 'kraska_login.json'), "w") as f:
				json.dump(self.login_data, f )
	
	# #################################################################################################
		
	def login(self):
		username = self.cp.get_setting("kruser")
		password = self.cp.get_setting("krpass")

		if not username or not password:
			raise KraskaLoginFail(self.cp._("Login data for kra.sk not provided"))
			
		try:
			data = self.call_kraska_api('/api/user/login', {'data': {'username': username, 'password': password}})
		except Exception as e:
			self.cp.log_error('Kraska login error:\n%s' % traceback.format_exc())
			raise KraskaLoginFail( str(e) )

		if not "session_id" in data:
			raise KraskaLoginFail("%s" % data.get('msg', self.cp._("Wrong response to login command")))

		self.login_data['token'] = data['session_id']

	# #################################################################################################

	def refresh_login_data(self, try_nr=0):
		try:
			login_checksum = self.cp.get_settings_checksum(('kruser', 'krpass',))
			
			if 'token' not in self.login_data or self.login_data.get('checksum','') != login_checksum:
				# data not loaded from cache or data from other account stored - do fresh login
				self.login_data = { 'checksum': login_checksum }
				self.login()
			
			if 'token' in self.login_data:
				if not 'expiration' in self.login_data or self.login_data.get('load_time', 0) + (3600*24) < int(time()):
					self.get_user_info()
					
				if int(time()) > self.login_data['expiration']:
					self.cp.log_error("Subscription for kra.sk expired")
			
		except Exception as e:
			if try_nr == 0 and 'token' in self.login_data:
				del self.login_data['token']
				
				# something failed try once more time with fresh login
				self.refresh_login_data(try_nr+1)
			else:
				self.cp.log_error("Kraska login failed: %s" % str(e))
				self.save_login_data()
				
		
		return self.login_data.get('days_left', -1)
	
	# #################################################################################################
	
	def get_expiration(self, subscripted_until ):
		if not subscripted_until:
			return 0
		
		# 2022-09-14 18:43:29
		return int(mktime(datetime.strptime(subscripted_until, '%Y-%m-%d %H:%M:%S').timetuple()))
		
	# #################################################################################################
	
	def get_user_info(self):
		try:
			data = self.call_kraska_api('/api/user/info')
		except Exception as e:
			self.cp.log_error('Kraska get user info fail:\n%s' % traceback.format_exc())
			raise KraskaApiError( str(e) )

		if 'data' not in data:
			raise KraskaLoginFail("%s" % data.get('msg', self.cp._("Failed to get user informations")))
		
		self.login_data['load_time'] = int(time())
		self.login_data['days_left'] = data['data'].get('days_left', 0)
		self.login_data['expiration'] = self.get_expiration( data['data'].get('subscribed_until') )
		self.save_login_data()
		
		return data['data']

	# #################################################################################################
	
	def call_kraska_api(self, endpoint, data=None):
		if data is None:
			data = {}

		timeout = int(self.cp.get_setting('loading_timeout'))
		if timeout == 0:
			timeout = None

		if 'token' in self.login_data:
			data.update({'session_id': self.login_data['token']})

		response = requests.post(BASE + endpoint, json=data, timeout=timeout)
		
		if response.status_code != 200:
			raise KraskaApiError(self.cp._("Wrong response status code") + ": %d" % response.status_code)
			
		return response.json()

	# #################################################################################################
	
	def resolve(self, ident):
		try:
			return self._resolve( ident )
		except KraskaApiError:
			# API Error - try once more with new login try
			return self._resolve( ident )
		
	# #################################################################################################
	
	def _resolve(self, ident):
		self.refresh_login_data()
		
		token = self.login_data.get('token')

		if not token:
			raise KraskaLoginFail(self.cp._("Wrong kra.sk login data"))
		
		if int(time()) > self.login_data.get('expiration', 0):
			raise KraskaLoginFail(self.cp._("Subscription expired"))

		try:
			data = self.call_kraska_api('/api/file/download', {"data": {"ident": ident}})
			return data.get("data", {}).get('link')
		except KraskaApiError:
			# pravdepodobne neplatný token
			self.login_data = {}
			raise
			
		except Exception:
			self.login_data = {}
			self.cp.log_error('Kraska resolve error:\n%s' % traceback.format_exc())
			raise KraskaResolveException(self.cp._("Failed to resolve file address"))

	# #################################################################################################
