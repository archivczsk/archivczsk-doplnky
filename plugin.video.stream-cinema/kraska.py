import os
import json
import traceback
from hashlib import md5
import requests
from datetime import datetime
from time import time, mktime

BASE = 'https://api.kra.sk'

# #################################################################################################

class ResolveException(Exception):
	pass

class KraskaLoginFail(Exception):
	pass

class KraskaApiError(Exception):
	pass

class KraskaNoSubsctiption(Exception):
	pass


def _log_dummy(message):
	print('[KRASKA]: ' + message )
	pass

# #################################################################################################

class Kraska:
	def __init__(self, username=None, password=None, data_dir=None, log_function=None):
		self.username = username
		self.password = password
		self.data_dir = data_dir
		self.log_function = log_function if log_function else _log_dummy
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
					self.log_function("Kraska login data loaded from cache")
			except:
				pass

	# #################################################################################################
	
	def save_login_data(self):
		if self.data_dir:
			with open(os.path.join(self.data_dir, 'kraska_login.json'), "w") as f:
				json.dump(self.login_data, f )
	
	# #################################################################################################
		
	def login(self):
		if not self.username or len(self.username) == 0 or not self.password or len(self.password) == 0:
			 raise KraskaLoginFail( "Nezadané prihlasovacie údaje" )
			
		try:
			data = self.call_kraska_api('/api/user/login', {'data': {'username': self.username, 'password': self.password}})
		except Exception as e:
			self.log_function('kra err login: {}'.format(traceback.format_exc()))
			raise KraskaLoginFail( str(e) )

		if not "session_id" in data:
			raise KraskaLoginFail( "%s" % data.get('msg', "Chybná odpoveď na príkaz login") )

		self.login_data['token'] = data['session_id']

	# #################################################################################################

	def refresh_login_data(self, try_nr=0):
		try:
			login_checksum = self.get_chsum()
			
			if len(self.login_data) == 0 or self.login_data.get('checksum','') != login_checksum:
				# data not loaded from cache or data from other account stored - do fresh login
				self.login_data = { 'checksum': login_checksum }
				self.login()
			
			if 'token' in self.login_data:
				if not 'expiration' in self.login_data or self.login_data.get('load_time', 0) + (3600*24) < int(time()):
					self.get_user_info()
					
				if int(time()) > self.login_data['expiration']:
					self.log_function("Platnosť Kraska predplatného vypršala")
			
		except Exception as e:
			if try_nr == 0 and 'token' in self.login_data:
				del self.login_data['token']
				
				# something failed try once more time with fresh login
				self.refresh_login_data(try_nr+1)
			else:
				self.log_function( "Kraska login failed: %s" % str(e) )
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
			self.log_function('kra get user info fail: {}'.format(traceback.format_exc()))
			raise KraskaApiError( str(e) )

		if 'data' not in data:
			raise KraskaLoginFail( "%s" % data.get('msg', "Nepodarilo sa získať informácie o užívateľovi") )
		
		self.login_data['load_time'] = int(time())
		self.login_data['days_left'] = data['data'].get('days_left', 0)
		self.login_data['expiration'] = self.get_expiration( data['data'].get('subscribed_until') )
		self.save_login_data()
		
		return data['data']

	# #################################################################################################
	
	def call_kraska_api(self, endpoint, data=None):
		if data is None:
			data = {}
			
		if 'token' in self.login_data:
			data.update({'session_id': self.login_data['token']})

		response = requests.post(BASE + endpoint, json=data)
		
		if response.status_code != 200:
			raise KraskaApiError("Wrong response status code: %d" % response.status_code)
			
		return response.json()

	# #################################################################################################
	
	def get_chsum(self):
		if not self.username or not self.password or len(self.username) == 0 or len( self.password) == 0:
			return None

		return md5(
			"{}|{}".format(self.password.encode('utf-8'),
						   self.username.encode('utf-8')).encode('utf-8')).hexdigest()

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
			raise KraskaLoginFail("Neplatné prihlasovacie údaje")
		
		if int(time()) > self.login_data.get('expiration', 0):
			raise KraskaLoginFail("Platnosť predplatného vypršala")

		try:
			data = self.call_kraska_api('/api/file/download', {"data": {"ident": ident}})
			return data.get("data", {}).get('link')
		except KraskaApiError:
			# pravdepodobne neplatný token
			self.login_data = {}
			raise
			
		except Exception as e:
			self.login_data = {}
			self.log_function('kra resolve error: {}'.format(traceback.format_exc()))
			raise ResolveException("Nepodarilo sa resolvnúť súbor")

	# #################################################################################################
