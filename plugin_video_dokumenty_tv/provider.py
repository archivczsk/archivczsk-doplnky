# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.cache import SimpleAutokeyExpiringCache, ExpiringLRUCache
from tools_archivczsk.compat import urlparse
from functools import partial
import sys
import re
from .video_resolver import get_resolver_by_url

try:
	from bs4 import BeautifulSoup
	bs4_available = True
except:
	bs4_available = False

COMMON_HEADERS = {
	'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36',
}

# ##################################################################################################################

class DokumentyTvContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None, http_endpoint=None):
		CommonContentProvider.__init__(self, 'Dokumenty.tv', settings=settings, data_dir=data_dir)
		self.http_endpoint = http_endpoint
		self.last_hls = None
		self.req_session = self.get_requests_session()
		self.req_session.headers.update(COMMON_HEADERS)
		self.img_cache = SimpleAutokeyExpiringCache(120)
		self.req_cache = ExpiringLRUCache(30, 600)

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, use_cache=True, json=False):
		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = 'https://www.dokumenty.tv/' + endpoint

		if use_cache and params == None:
			soup = self.req_cache.get(url)

			if soup != None:
				return soup

		req_headers = {
			'Accept-Encoding': 'identity',
		}

		try:
			response = self.req_session.get(url, params=params, headers=req_headers)
		except Exception as e:
			raise AddonErrorException(self._('Request to remote server failed. Try to repeat operation.') + '\n%s' % str(e))

		if response.status_code == 200:
			if json:
				soup = response.json()
			else:
				soup = BeautifulSoup(response.content, "html.parser")

			if use_cache and params == None:
				self.req_cache.put(url, soup)

			return soup
		else:
			raise AddonErrorException(self._('HTTP response code') + ': %d' % response.status_code)

	# ##################################################################################################################

	def root(self):
		if not bs4_available:
			self.show_info(self._("In order addon to work you need to install the BeautifulSoup4 using your package manager. Search for package with name:\npython{0}-beautifulsoup4 or python{0}-bs4)").format('3' if sys.version_info[0] == 3 else ''))
			return

		self.add_search_dir()
		self.add_dir(self._("Home"), cmd=self.list_category)
		self.add_dir(self._("Geography and traveling"), cmd=self.list_category, name='geografie-a-cestovani')
		self.add_dir(self._("History and retro"), cmd=self.list_category, name='historie-retro')
		self.add_dir(self._("Catastrophic"), cmd=self.list_category, name='katastroficke')
		self.add_dir(self._("Conspiracy"), cmd=self.list_category, name='konspirace')
		self.add_dir(self._("Crime"), cmd=self.list_category, name='krimi')
		self.add_dir(self._("Thinking"), cmd=self.list_category, name='myseni')
		self.add_dir(self._("Politics"), cmd=self.list_category, name='politika')
		self.add_dir(self._("Nature and animals"), cmd=self.list_category, name='priroda')
		self.add_dir(self._("Technology and science"), cmd=self.list_category, name='technika-veda')
		self.add_dir(self._("War and army"), cmd=self.list_category, name='valka-armada')
		self.add_dir(self._("Universe and UFO"), cmd=self.list_category, name='vesmir-ufo')
		self.add_dir(self._("Mysteries and mythology"), cmd=self.list_category, name='zahady')
		self.add_dir(self._("Lifestyle and sport"), cmd=self.list_category, name='zivotni-styl-sport')

	# ##################################################################################################################

	def search(self, keyword, search_id):
		return self.list_category('', params={ 's': keyword })

	# ##################################################################################################################

	def load_info_labels(self, url):
		soup = self.call_api(url)
		date_str = soup.find('div', {'class': 'entry-meta'}).find('span', {'class': 'entry-date'}).get_text().replace(' ', '')

		plot = soup.find('div', {'class': 'entry-content'}).find_all('p')[-1].get_text()

		meta = soup.find('div', {'class': 'entry-meta-bottom'})

		categories = [t.get_text() for t in meta.find('span', {'class': 'entry-category'}).find_all('a')]
		tags = [t.get_text() for t in meta.find('span', {'class': 'entry-tags'}).find_all('a')]

		return {
			'plot': '[%s]\n%s' % (date_str, plot),
			'genre': ', '.join(categories + tags)
		}

	# ##################################################################################################################

	def list_category(self, name='', params=None):
		if name != '' and not name.startswith('http'):
			name = 'category/' + name + '/'

		soup = self.call_api(name, params=params)

		for video_div in soup.find_all("div", { "id": re.compile( 'post-([0-9]+)' ) }):
			url = video_div.find('a', {'class': "thumbnail-link" })['href']
			img = video_div.find('img')['src']
			title = video_div.find('h2', {'class': 'entry-title'}).find('a').get_text()

			self.add_dir(self.fix_title(title), img, info_labels=partial(self.load_info_labels, url=url), cmd=self.list_videos, url=url)

		next_page = soup.find('a', {'class': 'next page-numbers'})

		if next_page != None:
			self.add_next(cmd=self.list_category, name=next_page['href'])


	# ##################################################################################################################

	def load_video_info(self, resolver):
		return {
			'plot': self.fix_title(resolver.get_title() or ''),
			'duration': resolver.get_video_duration()
		}

	# ##################################################################################################################

	def fix_title(self, title):
		return title.replace('-dokument', '').replace('(www.Dokumenty.TV)', '').replace('  ', ' ').strip()

	# ##################################################################################################################

	def list_videos(self, url):
		soup = self.call_api(url)

		entry = soup.find('div', {'class': 'entry-content'})

		i = 1
		for video_div in entry.find_all('iframe'):
			video_url = video_div['src']

			if video_url.startswith('//'):
				video_url = 'https:' + video_url

			if not video_url.startswith('http'):
				continue

			video_resolver = get_resolver_by_url(self, video_url)

			if not video_resolver:
				self.log_error("Not supported provider: %s" % video_url)
				raise AddonErrorException(self._("Not supported video provider: {provider}").format(provider=urlparse(video_url).netloc))

			img_key = self.img_cache.put(video_resolver)

			self.add_video( self._("Episode") + ' ' + str(i), img=self.http_endpoint + '/img/' + img_key, info_labels=partial(self.load_video_info, resolver=video_resolver), cmd=self.resolve_video, resolver=video_resolver)
			i += 1

	# ##################################################################################################################

	def get_hls_info(self, stream_key):
		return {
			'url': self.last_hls,
			'bandwidth': stream_key,
		}

	# ##################################################################################################################

	def resolve_streams(self, url, max_bitrate=None):
		streams = self.get_hls_streams(url, requests_session=self.req_session, max_bitrate=max_bitrate)

		self.last_hls = url

		for stream in (streams or []):
			stream['url'] = stream_key_to_hls_url(self.http_endpoint, stream['bandwidth'])
#			self.log_debug("HLS for bandwidth %s: %s" % (stream['bandwidth'], stream['url']))

		return streams

	# ##################################################################################################################

	def resolve_video(self, resolver):
		self.ensure_supporter()

		if resolver.name == 'Youtube':
			youtube_params = {
				'url': resolver.url,
#				'title': video_title
			}

			return self.call_another_addon('plugin.video.yt', youtube_params, 'resolve')

		resolved_video = resolver.get_video_url()
		self.log_debug("Resolved stream: Type: %s, URL: %s" % (resolved_video['type'], resolved_video['url']))

		if not resolved_video['url']:
			return

		if resolved_video['type'] == 'hls':
			stream_links = self.resolve_streams(resolved_video['url'], self.get_setting('max_bitrate'))
		elif resolved_video['type'] == 'mp4':
			stream_links = [{
				'url': resolved_video['url'],
				'bandwidth': 1
			}]
		else:
			stream_links = []

		video_title = resolver.get_title() or 'Video'
		video_settings = {}

		if resolved_video.get('headers'):
			video_settings['extra-headers'] = resolved_video.get('headers')

		for one in stream_links:
			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('resolution', 'x???').split('x')[1] + 'p'
			}
			self.add_play(self.fix_title(video_title), one['url'], info_labels=info_labels, settings=video_settings)

	# ##################################################################################################################
