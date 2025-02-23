# -*- coding: utf-8 -*-
import os
import json
from collections import OrderedDict

try:
	from urlparse import urlparse, urlunparse, parse_qs

except:
	from urllib.parse import urlparse, urlunparse, parse_qs

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

			json_data = OrderedDict()
			for k, v in parse_qs(body).items():
				if len(v) == 1:
					json_data[k] = v[0]
				else:
					json_data[k] = v

		except:
			json_data = None

	params = OrderedDict()
	for k, v in parse_qs(u.query).items():
		if len(v) == 1:
			params[k] = v[0]
		else:
			params[k] = v

	data = {
		'request': {
			'method': request.method,
			'url': urlunparse((u.scheme, u.netloc, u.path, '', '', '')),
			'full_url': request.url,
			'params': params,
			'headers': OrderedDict(request.headers),
			'data': json_data,
			'data_raw': str(request.body)
		},
		'response': {
			'status_code': response.status_code,
			'headers': OrderedDict(response.headers),
			'body': json_response,
			'data_raw': str(response.text)
		}
	}

	try:
		with open( os.path.join('/tmp/', '%03d_%s.json' % (__debug_nr, file_name)), 'w') as f:
			json.dump(data, f)
	except:
		pass
