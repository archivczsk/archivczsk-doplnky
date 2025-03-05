from tools_archivczsk.parser.js import get_js_data
from tools_archivczsk.compat import urlparse
import json

# ##################################################################################################################

def get_duration(dur):
	duration = 0
	l = dur.strip().split(":")
	for pos, value in enumerate(l[::-1]):
		duration += int(value) * 60 ** pos
	return duration

# ##################################################################################################################

class GenericResolver(object):
	def __init__(self, content_provider, url):
		self.name = 'Generic'
		self.url = url
		self.cp = content_provider
		self.video_url = None
		self.video_url_type = None
		self.video_title = None
		self.video_headers = {}
		self.video_img = None
		self.video_duration = None
		self.data_readed = False

	def read_data_if_needed(self):
		if self.data_readed == False:
			self.read_data()

	def get_title(self):
		self.read_data_if_needed()
		return self.video_title

	def get_video_url(self):
		self.read_data_if_needed()
		return {
			'url': self.video_url,
			'type': self.video_url_type,
			'headers': self.video_headers
		}

	def get_video_duration(self):
		self.read_data_if_needed()
		return self.video_duration

	def get_video_img(self):
		self.read_data_if_needed()
		return self.video_img

	def read_data(self):
		pass

# ##################################################################################################################

class OkResolver(GenericResolver):
	def __init__(self, *args, **kwargs):
		super(OkResolver, self).__init__(*args, **kwargs)
		self.name = 'ok.ru'

	def read_data(self):
		self.cp.log_debug("Reading data from url: %s" % self.url)
		soup = self.cp.call_api(self.url)

		player_data = soup.find('div', {'data-module': "OKVideo"})
		js = get_js_data(player_data.get('data-options'))
		js = get_js_data(js['flashvars']['metadata'])
#		self.cp.log_debug('JS DATA\n%s' % str(js))

		self.video_url = js.get('hlsManifestUrl') or js.get('ondemandHls')

		if self.video_url:
			self.video_url = self.video_url.replace('\u0026','&')
			self.video_url_type = 'hls'
		elif js.get('videos'):
			self.video_url = js['videos'][-1].get('url')
			self.video_url_type = 'mp4'
			self.video_headers['Origin'] = 'https://ok.ru'
			self.video_headers['Referer'] = self.url

		if not self.video_url:
			# throw some exception here and let the addon crash - we want bug reports from users in order know, that something on site changed
			raise Exception("Failed to resolve video. Not supported json data:\n%s" % str(js))

		video_div = soup.find('div', {'class': 'vid-card_cnt_w'})

		self.video_img = video_div.find('img')['src']

		try:
			self.video_title = video_div.find('img')['alt']
		except:
			pass

		if not self.video_title:
			self.video_title = video_div.find('span', {'class': 'vid-card_n'}).get_text() or ""

		self.video_duration = get_duration(video_div.find('div', {'class': 'vid-card_duration'}).get_text())
		self.data_readed = True

# ##################################################################################################################

class DailymotionResolver(GenericResolver):
	def __init__(self, *args, **kwargs):
		super(DailymotionResolver, self).__init__(*args, **kwargs)
		self.name = 'Dailymotion'

	def read_data(self):
		video_id = urlparse(self.url).path.split('/')[-1]
		player_data = self.cp.call_api('https://www.dailymotion.com/player/metadata/video/' + video_id, json=True)

		self.video_title = player_data.get('title')
		self.video_duration = player_data.get('duration')
		self.video_url = player_data.get('qualities', {}).get('auto', [{}])[0].get('url')
		self.video_url_type = 'hls'
		self.video_img = player_data.get('thumbnails', {}).get('480')
		self.data_readed = True

# ##################################################################################################################

class YoutubeResolver(GenericResolver):
	def __init__(self, *args, **kwargs):
		# this resolver actually does nothing - resolving will be done by youtube addon
		super(YoutubeResolver, self).__init__(*args, **kwargs)
		self.name = 'Youtube'

# ##################################################################################################################

def get_resolver_by_url(content_provider, url):
	if 'ok.ru' in url:
		return OkResolver(content_provider, url)
	elif 'dailymotion.com' in url:
		return DailymotionResolver(content_provider, url)
	elif 'youtube.com' in url:
		return YoutubeResolver(content_provider, url)

	return None

# ##################################################################################################################
