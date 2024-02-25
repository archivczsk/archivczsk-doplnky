# -*- coding: utf-8 -*-
import os
import json
from collections import OrderedDict

try:
	from urlparse import urlparse, urlunparse, parse_qsl

except:
	from urllib.parse import urlparse, urlunparse, parse_qsl

__debug_nr = 0


def dump_json_request(response):
	global __debug_nr
	__debug_nr += 1

	request = response.request

	u = urlparse(request.url)

	file_name = urlunparse( ('', u.netloc, u.path, '', '', '') )[2:].replace('/', '_')

	try:
		json_response = response.json()
	except:
		json_response = {}

	try:
		json_data = json.loads(request.body)
	except:
		json_data = None

	if not json_data:
		try:
			try:
				body = request.body.decode('utf-8')
			except:
				body = request.body
			json_data = OrderedDict(parse_qsl(body))
		except:
			json_data = None

	data = {
		'request': {
			'method': request.method,
			'url': urlunparse((u.scheme, u.netloc, u.path, '', '', '')),
			'full_url': request.url,
			'params': OrderedDict(parse_qsl(u.query)),
			'headers': OrderedDict(request.headers),
			'data': json_data,
		},
		'response': {
			'status_code': response.status_code,
			'body': json_response
		}
	}

	with open( os.path.join('/tmp/', '%03d_%s.json' % (__debug_nr, file_name)), 'w') as f:
		json.dump(data, f)
