# -*- coding: utf-8 -*-

import re, sys
from tools_archivczsk.parser.js import get_js_data
from tools_archivczsk.compat import urlparse, urljoin
import json
import base64
import string
import re

try:
	xrange
except:
	xrange = range

try:
	unicode
except:
	unicode = str

def dump_html_response(name, response):
	with open('/tmp/' + name + '.html', 'wb') as f:
		f.write(response.content)

# ##################################################################################################################

class BasicStreamProvider(object):
	def __init__(self, sp, name):
		self.cp = sp.cp
		self.req_session = sp.req_session
		self.beautifulsoup = sp.beautifulsoup
		self.name = name

	# ##################################################################################################################

	def log_debug(self, s):
		self.cp.log_debug('[{}] {}'.format(self.name, s))

	# ##################################################################################################################

	def log_error(self, s):
		self.cp.log_error('[{}] {}'.format(self.name, s))

	# ##################################################################################################################

	def log_info(self, s):
		self.cp.log_info('[{}] {}'.format(self.name, s))

	# ##################################################################################################################

	def log_exception(self):
		self.cp.log_exception()

	# ##################################################################################################################

	def get_soup(self, url, dupe_ref=False):
		headers = {}

		if dupe_ref:
			headers['Referer'] = 'https://dupe.cz/'

		self.log_debug("Requesting URL: %s" % url)
		response = self.req_session.get(url, headers=headers)
		response.raise_for_status()

		return self.beautifulsoup(response.content, "html.parser"), response.url

	# ##################################################################################################################

class OkRuStreamProvider(BasicStreamProvider):
	def resolve(self, url):
		soup, url = self.get_soup(url)

		try:
			player_data = soup.find('div', {'data-module': "OKVideo"})
			js = get_js_data(player_data.get('data-options'))
			js = get_js_data(js['flashvars']['metadata'])
		except:
			self.log_error("Failed to get player configuration from url %s" % url)
			self.log_exception()
			return {}

#		self.log_debug("Player config:\n%s" % json.dumps(js))

		if 'hlsMasterPlaylistUrl' in js:
			return {
				'type': 'hls',
				'url': urljoin(url, js['hlsMasterPlaylistUrl'].replace('\u0026','&')),
			}

		if 'hlsManifestUrl' in js:
			return {
				'type': 'hls',
				'url': urljoin(url, js['hlsManifestUrl'].replace('\u0026','&')),
			}

		video_url = None

		if js.get('videos'):
			video_url = urljoin(url, js['videos'][-1]['url'].replace('\u0026','&'))

		if not video_url:
			self.log_error("Unsupported player data - can't get video URL:\n%s" % json.dumps(js))
			return {}

		self.log_debug("player data:\n%s" % json.dumps(js))

		subtitles = []
		if (js.get('movie') or {}).get('subtitleTracks'):
			for s in js['movie']['subtitleTracks']:
				title = s.get('title') or ''
				if title.endswith('[CC]'):
					continue
				subtitles.append({
					'title': title,
					'lang': s.get('language', 'unk'),
					'url': urljoin(url, s['url'].replace('\u0026','&')),
					'forced': title.endswith('[Forced]')
				})

		return {
			'type': 'mp4',
			'url': video_url,
			'subtitles': subtitles,
		}

	# ##################################################################################################################

class VoeStreamProvider(BasicStreamProvider):
	def check_redirect(self, soup, url):
		self.log_debug("Checking for redirect page")
		try:
			if soup.find('head').find('title').get_text().strip() != 'Redirecting...':
				return soup, url
		except:
			self.log_error("Voe redirect check failed")
			self.log_exception()

		url = re.findall(r"window.location.href\s*=\s*'(.*)'", soup.find('script').string)[0]
		self.log_debug("Extracted redirect page: %s" % url)
		return self.get_soup(url)

	# ##################################################################################################################

	def deobfuscate(self, obfuscated_json):
		def rot13(text):
			"""Apply ROT13 cipher to the text (only affects letters)."""
			result = ""
			for char in text:
				code = ord(char)
				if 65 <= code <= 90:  # A-Z
					code = ((code - 65 + 13) % 26) + 65
				elif 97 <= code <= 122:  # a-z
					code = ((code - 97 + 13) % 26) + 97
				result += chr(code)
			return result

		def replace_patterns(text):
			"""Replace specific patterns with underscores."""
			patterns = ['@$', '^^', '~@', '%?', '*~', '!!', '#&']
			for pattern in patterns:
				text = text.replace(pattern, '')
			return text

		def decode_base64(text):
			"""Decode base64 encoded string."""
			try:
				return base64.b64decode(text).decode('utf-8', errors='replace')
			except Exception as e:
				self.log_error("Base64 decode error: %s" % str(e))
				return None

		def shift_chars(text, shift):
			"""Shift character codes by specified amount."""
			return ''.join([chr(ord(char) - shift) for char in text])

		def reverse_string(text):
			"""Reverse the string."""
			return text[::-1]

		"""Deobfuscate the JSON data using the new method."""
		try:
			data = json.loads(obfuscated_json)
			if isinstance(data, list) and len(data) > 0 and isinstance(data[0], (str, unicode,)):
				obfuscated_string = data[0]
			else:
				self.log_error("Input doesn't match expected format.")
				return None
		except json.JSONDecodeError:
			self.log_error("Invalid JSON input.")
			return None

		try:
			step1 = rot13(obfuscated_string)
			step2 = replace_patterns(step1)
			step4 = decode_base64(step2)
			if not step4:
				return None
			step5 = shift_chars(step4, 3)
			step6 = reverse_string(step5)
			step7 = decode_base64(step6)
			if not step7:
				return None

			result = json.loads(step7)
			return result
		except Exception as e:
			self.log_exception()
			return None

	# ##################################################################################################################

	def resolve(self, url):
		soup, url = self.get_soup(url)
		soup, url = self.check_redirect(soup, url)

		def find_player_config():
			# Look for the new obfuscated data pattern
			for script in soup.find_all('script'):
				if not script.string:
					continue

				# Look for JSON arrays that might contain obfuscated data
				for match in re.findall(r'\[\"[^\"]+\"\]', script.string):

					result = self.deobfuscate(match)

					if result and isinstance(result, dict):
						return result
			return {}

		config = find_player_config()
		self.log_debug("Deobfuscated player config:\n%s" % json.dumps(config))

		subtitles = []
		for s in (config.get('captions') or []):
			subtitles.append({
				'title': s.get('label') or 'Subtitles',
				'url': urljoin(url, s['file']),
			})

		if config.get('source'):
			video_url = config['source']
			video_type = 'hls' if urlparse(video_url).path.endswith('.m3u8') else "unknown"
			self.log_debug("Found HLS stream URL: %s" % video_url)
		elif config.get('direct_access_url'):
			self.log_debug("Found direct stream URL")
			video_type = 'mp4'
			video_url = urljoin(url, config['direct_access_url'])
		else:
			self.log_error("Unsupported player config:\n%s" % json.dumps(config))
			return {}

		return {
			'type': video_type,
			'url': video_url,
			'subtitles': subtitles,
		}

# ##################################################################################################################

class HgEvStreamProvider(BasicStreamProvider):
	# StreamHG (HG) and Earnvids (EV)

	def resolve(self, url):
		digs = string.digits + string.ascii_lowercase + string.ascii_uppercase
		soup, url = self.get_soup(url, dupe_ref=True)

		def int2base(x, base):
			if x < 0:
				sign = -1
			elif x == 0:
				return digs[0]
			else:
				sign = 1

			x *= sign
			digits = []

			if sys.version_info[0] < 3:
				while x:
					digits.append(digs[int(x % base)])
					x = int(x / base)
			else:
				while x:
					digits.append(digs[x % base])
					x = x // base

			if sign < 0:
				digits.append('-')

			digits.reverse()

			return ''.join(digits)

		def decrypt_packed(s):
			def unpack(p, a, c, k, e=None, d=None):
				for i in xrange(c-1,-1,-1):
					if k[i]:
						p = re.sub('\\b'+int2base(i,a)+'\\b', k[i], p)
				return p
			return eval('unpack' + s[s.find('}(')+1:].strip()[:-1])

		for s in soup.find_all('script'):
			if s.string and s.string.startswith('eval('):
				js = decrypt_packed(s.string)
				links = re.findall(r"var links=({.*?});", js)[0]
				self.log_debug("Found links: %s" % links)

				for l in eval(links).values():
					u = urlparse(l)
					if u.path.endswith('.m3u8') and u.query:
						return {
							'type': 'hls_multiaudio',
							'url': urljoin(url, l),
						}
		return {}

# ##################################################################################################################
class SupStreamProvider(BasicStreamProvider):
	# StreamUP

	def resolve(self, url):
		filecode = urlparse(url).path[1:]
		config = self.req_session.get('https://strmup.cc/ajax/stream', params={'filecode': filecode}, headers={'Referer': url}).json()

		subtitles = []
		for s in (config.get('subtitles') or []):
			subtitles.append({
				'title': s.get('language') or 'Subtitles',
				'url': urljoin(url, s['file_path']),
			})

		return {
			'type': 'hls',
			'url': config['streaming_url'],
			'subtitles': subtitles,
		}


# ##################################################################################################################

class StreamProvider(object):
	def __init__(self, content_provider):
		self.cp = content_provider

		self.req_session = self.cp.get_requests_session()
		self.beautifulsoup = self.cp.get_beautifulsoup()

		self.resolvers = {
			'OK-RU': OkRuStreamProvider,
			'VO': VoeStreamProvider,
			'HG': HgEvStreamProvider,
			'EV': HgEvStreamProvider,
			'SUP': SupStreamProvider
		}

	# ##################################################################################################################

	def is_supported(self, provider_name):
#		return provider in ('OK-RU', 'VO', 'SKTOR', 'HG, 'EV', 'SUP)

		# ABS - protected by CloudFlate "Just a moment..." anti boot script
		# MOON - links hidded inside of obfuscated javascript loaded from no one knows ...
		# U4S - a russian site with all kind of anti debug protections + tracks everything

		if provider_name in ('ABS', 'MOON', 'U4S'):
			return False

		return True

	# ##################################################################################################################

	def resolve(self, provider_name, url):
		self.cp.log_info("Resolving video data from URL %s using provider %s" % (url, provider_name))

		r = self.resolvers.get(provider_name)

		if not r:
			self.cp.log_error("No stream resolver for provider %s found" % provider_name)
			return {}

		return r(self, provider_name).resolve(url)

	# ##################################################################################################################
