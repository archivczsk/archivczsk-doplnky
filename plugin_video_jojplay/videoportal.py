# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.compat import urlparse, parse_qsl
from tools_archivczsk.cache import ExpiringLRUCache

class JojPlayRedirect(Exception):
	pass

# ##################################################################################################################

class JojVideoportal(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()
		self.req_cache = ExpiringLRUCache(30, 600)
		self.beautifulsoup = self.cp.get_beautifulsoup()

	# ##################################################################################################################

	def _(self, s):
		return self.cp._(s)

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, use_cache=True):
		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = 'https://www.joj.sk/' + endpoint

		if use_cache and params == None:
			soup = self.req_cache.get(url)

			if soup != None:
				return soup

		req_headers = {
		}

		try:
			response = self.req_session.get(url, params=params, headers=req_headers)
		except Exception as e:
			raise AddonErrorException(self._('Request to remote server failed. Try to repeat operation.') + '\n%s' % str(e))

		self.cp.log_debug("Requested URL: %s" % response.request.url)


		if response.url.startswith('https://play.joj.sk/'):
			raise JojPlayRedirect(response.url)

		if response.status_code == 200:
			soup = self.beautifulsoup(response.content, "html.parser")

			if use_cache and params == None:
				self.req_cache.put(url, soup)

			return soup
		else:
			raise AddonErrorException(self._('HTTP response code') + ': %d' % response.status_code)

	# ##################################################################################################################

	def root(self):
		soup = self.call_api('relacie')

		for a in soup.find_all('a'):
			if a.get('v-if'):
				title = a.find('img').get('alt')
				img = a.find('img').get('src')
				self.cp.add_dir(title, img, cmd=self.list_joj_show, show_url=a.get('href'))


	# ##################################################################################################################

	def list_joj_show(self, show_url):
		soup = self.call_api(show_url)
		div = soup.find('div', {'class': 'text-joj-black'}).find('a', {'class': 'j-button--variant-primary'})

		if div != None:
			url = div.get('href')
			return self.handle_jojplay_redirect(url)

	# ##################################################################################################################

	def handle_jojplay_redirect(self, url, video=False):
		# possible redirect formats
		# https://play.joj.sk/series/OY8pxTTH53PwSStzbSYW - Riskuj
		# https://play.joj.sk/tags/k6OKPpUwntmA0d1EvpmB - Iveta
		# https://play.joj.sk/screens/series?series=00Td2pUY3ndu7bvuxLTa - Ranc
		# https://play.joj.sk/player/LOiXEcZW1BfytMC5ildP?type=VIDEO' - Zradcovcia
		# https://play.joj.sk/player/inovujme-slovensko-s2018-e10?type=VIDEO -  Inovujeme Slovensko

		self.cp.log_debug("Trying to process JOJ Play redirect: %s" % url)

		u = urlparse(url)
		item_type = u.path.split('/')[1]
		item_id = u.path.split('/')[2]

		if item_type == 'screens':
			# convert this command to 'tags' - load original tag ID
			params = dict(set(parse_qsl(u.query)))
			doc = self.cp.jojplay.client.load_document_content(params.get('series'))
			item_id = doc['originalSeriesTagRef'].split('/')[-1]
			self.cp.log_debug("Series ID %s converted to tag ref: %s" % (params.get('series'), item_id))
			item_type = 'tags'

		if item_type in ('tags', 'series'):
			if video:
				# TODO: here it can happen, that we should play video, but we received ID for the whole show
				# but this happens only for few items, so I will ignore this problem for now
				pass

			self.cp.log_debug("Processing tag ref: %s" % item_id)
			return self.cp.list_tag(item_id)

		elif item_type == 'player':
			if video:
				# we should resolve video file
				items = self.cp.jojplay.client.get_videos_by_url(item_id)
				return self.cp.resolve_video(self.cp.jojplay._add_video_item(items[0]))
			else:
				doc = self.cp.jojplay.client.load_document('/videos/' + item_id)

				# find all tags from video document and select one, that type is "show" - we assume, that the first one is video parent show
				for tag_id in doc.get('tags', []):
					tag_id = tag_id.split('/')[-1]
					self.cp.log_debug("Found tag ID: %s" % tag_id)
					data = self.cp.jojplay.get_tag_data(tag_id)
					if data and data[0]['tagTypeRef'].endswith('1X9nXUOc9XbtobIcFdyA'):
						return self.cp.list_tag(tag_id)

		self.cp.show_info(self._("Unsupported JOJ Play redirect type") + ":\n" + url)

	# ##################################################################################################################
