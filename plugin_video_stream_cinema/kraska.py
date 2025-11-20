# -*- coding: utf-8 -*-

import os
import json
import traceback
import base64
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

class KraskaNoSubsctiption(KraskaLoginFail):
	pass


# #################################################################################################

class Kraska:
	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()
		self.login_data = {}
		self.load_login_data()

	# #################################################################################################

	def load_login_data(self):
		self.login_data = self.cp.load_cached_data('kraska_login')

		if self.login_data:
			self.cp.log_debug("Kraska login data loaded from cache")

		self.login_data['load_time'] = 0 # this will force reload of user data

	# #################################################################################################

	def save_login_data(self):
		self.cp.save_cached_data('kraska_login', self.login_data)

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

	def refresh_login_data(self, check_login_change=False, try_nr=0):
		try:
			login_checksum = self.cp.get_settings_checksum(('kruser', 'krpass',))

			if not self.get_token() or (check_login_change and self.login_data.get('checksum','') != login_checksum):
				# data not loaded from cache or data from other account stored - do fresh login
				self.login_data = { 'checksum': login_checksum }
				self.login()

			if self.get_token():
				if not 'expiration' in self.login_data or self.login_data.get('load_time', 0) + (3600*24) < int(time()):
					self.get_user_info()

				if int(time()) > self.login_data['expiration']:
					self.cp.log_error("Subscription for kra.sk expired")

		except Exception as e:
			if try_nr == 0 and 'token' in self.login_data:
				del self.login_data['token']

				# something failed try once more time with fresh login
				self.refresh_login_data(check_login_change, try_nr+1)
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

		if 'token' in self.login_data:
			data.update({'session_id': self.login_data['token']})

		response = self.req_session.post(BASE + endpoint, json=data)

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

		token = self.get_token()

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

	def get_token(self):
		return self.login_data.get('token')

	# #################################################################################################

	def list_files(self, parent=None, filter=None):
		self.refresh_login_data()

		data = self.call_kraska_api('/api/file/list', {'data': {'parent': parent, 'filter': filter}})
		return data

	# #################################################################################################

	def delete_file(self, filename):
		found = self.list_files(filter=filename).get('data', [])
		if len(found) == 1:
			for f in found:
				if f.get('name', None) == filename:
					self.delete(f.get('ident', None))
					return True

		return False

	# #################################################################################################

	def upload(self, data, filename):
		self.refresh_login_data()

		token = self.get_token()

		if not token:
			raise KraskaLoginFail(self.cp._("Wrong kra.sk login data"))

		item = self.call_kraska_api('/api/file/create', {'data': {'name': filename}, 'shared': False})

		if item and item.get('error', None) == 1205:
			if self.delete_file(filename):
				return self.upload(data, filename)

		if not item or 'data' not in item:
			self.cp.log_error('File upload error 1: {} / {}'.format(item, item.get('error', None)))
			raise KraskaApiError(self.cp._("Failed to upload file"))

		ident = item.get('data').get('ident', None)
		link = item.get('data').get('link', None)
		if ident is None or link is None:
			self.cp.log_error('File upload error 2: {}'.format(item))
			raise KraskaApiError(self.cp._("Failed to upload file"))

		bident = base64.b64encode(ident.encode('utf-8')).decode("utf-8")

		headers = {
			'Tus-Resumable': '1.0.0',
			'Upload-Metadata': 'ident {}'.format(bident),
			'Upload-Length': str(len(data)),
		}
		upload = self.req_session.post(link, headers=headers, allow_redirects=False)

		self.cp.log_debug('response headers: {}/{}'.format(upload.status_code, json.dumps(dict(upload.headers))))
		upload_url = upload.headers.get('location', None)

		if upload_url is None or upload.status_code != 201:
			self.cp.log_error('File upload error 3: {}'.format(item))
			self.delete(ident)
			raise KraskaApiError(self.cp._("Failed to upload file"))

		self.cp.log_debug('upload url: %s' % upload_url)

		headers = {
			'Tus-Resumable': '1.0.0',
			'Upload-Offset': '0',
			'Content-Type': 'application/offset+octet-stream',
		}
		ufile = self.req_session.patch('https://upload.kra.sk' + upload_url, data=data, headers=headers)

		if ufile.status_code != 204:
			self.cp.log_error('File upload error 4: {}'.format(ufile.status_code))
			self.delete(ident)

		self.cp.log_debug('upload ok: {}'.format(ufile))

	# #################################################################################################

	def delete(self, ident):
		self.refresh_login_data()
		return self.call_kraska_api('/api/file/delete', {'data': {'ident': ident}})

	# #################################################################################################
