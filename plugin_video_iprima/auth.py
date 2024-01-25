# -*- coding: utf-8 -*-

import re
#from ssl import VerifyFlags
import requests
import sys
import time
import datetime
import random
import math

try:
	from urlparse import urlparse, parse_qs
except ImportError:
	from urllib.parse import urlparse, parse_qs

from Plugins.Extensions.archivCZSK.engine import client

def performCredentialCheck(addon):
	username = addon.get_setting('username')
	password = addon.get_setting('password')
	if not username or not password:
		client.showInfo('Pro přehrávání pořadů je potřeba účet na iPrima.cz\n\nPokud účet nemáte, zaregistrujte se na auth.iprima.cz/user/register a pak zde Menu -> Nastavení vyplňte přihlašovací údaje.')
		return False
	return True

def generateDeviceId():
	d = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() * 1000

	template = 'd-xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'
	device_id = ''

	for index, char in enumerate(template):
		if char in {'x', 'y'}:
			r = int( (d + random.random() * 16) % 16 )
			device_id += '{:x}'.format(r) if char == 'x' else '{:x}'.format(r & 0x3 | 0x8)
			d = math.floor(d / 16)
		else:
			device_id += char

	return(device_id)

def getDeviceId(addon):
	device_id = addon.get_setting('deviceId')
	if not device_id:
#		log('Generating new device id', 2)
		device_id = generateDeviceId()
		addon.set_setting('deviceId', device_id)
		getAccessToken(addon, refresh=True, device=device_id)
	return device_id

def getAccessToken(addon, refresh=False, device=None):
	access_token = addon.get_setting('accessToken')
	user_id = addon.get_setting('userId')

	if not access_token or refresh:
#		log('Getting new access token', 2)
		username = addon.get_setting('username')
		password = addon.get_setting('password')
		device_id = device or getDeviceId(addon)

		authentication = login(username, password, device_id)

		access_token = authentication['access_token']
		user_id = authentication['user_uuid']

		addon.set_setting('accessToken', access_token)
		addon.set_setting('userId', user_id)

	return {'token': access_token, 'user_id': user_id}

def login(email, password, device_id):
	s = requests.Session()
	s.cookies.set('prima_device_id', device_id, domain='.iprima.cz')
	s.cookies.set('from_mobile_app', '1', domain='.iprima.cz')

	# Get login page
	login_page = s.get('https://auth.iprima.cz/oauth2/login', verify=False)
	login_page_content = login_page.text

	# Acquire CSRF token
	r_csrf = re.search('name="_csrf_token".*value="(.*)"', login_page_content)
	csrf_token = ''
	if r_csrf:
		csrf_token = r_csrf.group(1)
	else:
		client.showError('Nepodařilo se získat CSRF token')
		return

	# Log in
	do_login = s.post('https://auth.iprima.cz/oauth2/login', {
		'_email': email,
		'_password': password,
		'_csrf_token': csrf_token
	}, verify=False)

	if do_login.status_code != 200:
		client.showError('Přihlášení selhalo. Zkontrolujte přihlašovací jmémo a heslo.')
		return

	# select profile
	do_login = s.get('https://auth.iprima.cz/user/profile-select', verify=False)

	# Search for profile id and set it
	profile_id_search = re.search('data-edit-url="/user/profile-edit/(.*)"', do_login.text)

	if profile_id_search:
		profile_id = profile_id_search.group(1)
	else:
		client.showError('Nepodařilo se získat ID profilu')
		return

	do_profile_select = s.get('https://auth.iprima.cz/user/profile-select-perform/{}?continueUrl=/oauth2/authorize?response_type=code%26client_id=prima_sso%26redirect_uri=https://auth.iprima.cz/sso/auth-check%26scope=openid%20email%20profile%20phone%20address%20offline_access%26state=prima_sso%26auth_init_url=https://www.iprima.cz/%26auth_return_url=https://www.iprima.cz/?authentication%3Dcancelled'.format(profile_id), verify=False)

	# Acquire authorization code from profile select result
	parsed_auth_url = urlparse(do_profile_select.url)
	try:
		auth_code = parse_qs(parsed_auth_url.query)['code'][0]
	except KeyError:
		client.showError('Nepodařilo se získat autorizační kód, zkontrolujte přihlašovací údaje')
		return

	# Get access token
	get_token = s.post('https://auth.iprima.cz/oauth2/token', {
		'scope': 'openid+email+profile+phone+address+offline_access',
		'client_id': 'prima_sso',
		'grant_type': 'authorization_code',
		'code': auth_code,
		'redirect_uri': 'https://auth.iprima.cz/sso/auth-check'
	}, verify=False)
	if get_token.ok:
		return get_token.json()
	else:
		client.showError('Nepodařilo se získat access token')
		return
