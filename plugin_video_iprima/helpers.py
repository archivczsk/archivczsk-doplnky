# -*- coding: utf-8 -*-

import requests
from . import lookups
from . import auth
import json
import sys
from string import Template

from Plugins.Extensions.archivCZSK.engine import client

def getResourceUrl(resource, replacements):
	url = lookups.resources[resource]['path']
	if len(replacements) > 0:
		url = url.format(**replacements)
	return url

def getResourceMethod(resource):
	return lookups.resources[resource]['method']

def getResourceContentPath(resource):
	return lookups.resources[resource]['content_path']

def getResourcePostData(resource, options):
	template = Template(lookups.resources[resource]['post_data'])
	return template.substitute(**options)

def getJSONPath(data, keys):
	return getJSONPath(data[keys[0]], keys[1:]) if keys else data

def isPlayable(itemType):
	return lookups.item_types[itemType]['playable']

def requestResource(addon, resource, count=0, page=0, replace={}, postOptions={}, retrying=False):
	url = getResourceUrl(resource, replace)
	method = getResourceMethod(resource)
	options = {
		'count': str(count or lookups.shared['pagination']),
		'offset': str(page * lookups.shared['pagination'])
	}
	options.update(postOptions)
	authorization = auth.getAccessToken(addon, refresh=retrying)
	common_headers = {
		'Authorization': 'Bearer ' + authorization['token'],
		'x-prima-access-token': authorization['token'],
		'X-OTT-Access-Token': authorization['token'],
		'Content-Type': 'application/json',
		'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.35 Safari/537.36'
		}
	cookies = {
		'prima_device_id': auth.getDeviceId(addon),
		'prima_sso_logged_in': authorization['user_id']
	}
	if method == 'POST':
		data = getResourcePostData(resource, options).encode('utf-8')
		contentPath = getResourceContentPath(resource)
		request = postUrl(url, data, common_headers, cookies)
	else:
		request = getUrl(url, common_headers, cookies)
#	print("URL",url)
#	print("DAT",data,common_headers,cookies)
#	print("REQ",request.content)
	if request.ok:
		return getJSONPath(request.json(), contentPath) if method == 'POST' else request.json()
	elif request.status_code in {401, 403}:
		if retrying:
			client.showError('K tomuto obsahu nemáte přístup')
			sys.exit(1)
		return requestResource(addon, resource, count, page, replace, postOptions, retrying=True)
	client.showError('Server neodpovídá správně')

def getUrl(url, headers, cookies):
#	print('Requesting: ' + url)
	request = requests.get(
		url,
		timeout=20,
		headers=headers,
		cookies=cookies,
		verify=False
	)
	return request

def postUrl(url, data, headers, cookies):
#	print('Requesting: %s; with data: %s' % (url, data))
	request = requests.post(
		url,
		data=data,
		timeout=20,
		headers=headers,
		cookies=cookies,
		verify=False
	)
	return request
