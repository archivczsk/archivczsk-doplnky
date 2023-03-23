# -*- coding: utf-8 -*-

import requests
import re
from tools_archivczsk.contentprovider.exception import AddonErrorException

class Csfd(object):
	TOP100_ALL = 0
	TOP100_CSSK = 1
	TOP100_CS = 2
	TOP100_SK = 3

	def __init__(self, content_provider):
		self.cp = content_provider

		self.timeout = int(self.cp.get_setting('loading_timeout'))
		if self.timeout == 0:
			self.timeout = None

		self.req_session = requests.Session()
		self.req_session.headers.update({
			'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 OPR/92.0.0.0'
		})

	def call_csfd_api(self, endpoint, params=None, tv_cookies=False):
		if tv_cookies:
			cookies = {'tv_stations':'2%2C3%2C4%2C5%2C24%2C19%2C26%2C33%2C16%2C78%2C1%2C8%2C93%2C13%2C22%2C14%2C41%2C88', 'tv_tips_order':'2'}
		else:
			cookies = None

		response = self.req_session.get('https://www.csfd.cz/' + endpoint, params=params, cookies=cookies, timeout=self.timeout, verify=False)
		if response.status_code != 200:
			raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % response.status_code)

		return response.text

	def _get_similar_related(self, cid, selector):
		html = self.call_csfd_api('film/' + str(cid))
		
		vals = []
		
		data = re.search('<section.*?<h3>[\s]*?{}(.*?)</section>'.format(selector), html, re.S)
		if data:
			articles = re.findall('<article.*?href="/film/([0-9]+?)\-.*?".*?</article>', data.group(1), re.S)
			
			for article in articles:
				vals.append(article)

		return vals

	def get_related(self, cid):
		return self._get_similar_related(cid, 'Souvisej')

	def get_similar(self, cid):
		return self._get_similar_related(cid, 'Podobn')

	def get_tips(self):
		html = self.call_csfd_api('televize', params={ 'sort': 'rating'}, tv_cookies=True)

		vals = []
		articles = re.findall('<article.*?href="/film/([0-9]+?)-.*?</article>', html, re.S)

		if articles != None:
			for article in articles:
				vals.append(article)

		return vals

	def get_top(self, media_type, filter_type):
		filters = {
			'movie': {
				Csfd.TOP100_ALL: 'rlW0rKOyVwbjYPWipzyanJ4vBz51oTjfVzqyoaWyVwcoKFjvrJIupy9zpz9gVwchqJkfYPW5MJSlK3EiVwchqJkfYPWuL3EipvV6J10fVzEcpzIwqT9lVwcoKK0=',
				Csfd.TOP100_CSSK: 'rlW0rKOyVwbjYPWipzyanJ4vBwR5AljvM2IhpzHvBygqYPW5MJSlK2Mlo20vBz51oTjfVayyLKWsqT8vBz51oTjfVzSwqT9lVwcoKFjvMTylMJA0o3VvBygqsD==',
				Csfd.TOP100_CS: 'rlW0rKOyVwbjYPWipzyanJ4vBwRfVzqyoaWyVwcoKFjvrJIupy9zpz9gVwchqJkfYPW5MJSlK3EiVwchqJkfYPWuL3EipvV6J10fVzEcpzIwqT9lVwcoKK0=',
				Csfd.TOP100_SK: 'rlW0rKOyVwbjYPWipzyanJ4vBwVfVzqyoaWyVwcoKFjvrJIupy9zpz9gVwchqJkfYPW5MJSlK3EiVwchqJkfYPWuL3EipvV6J10fVzEcpzIwqT9lVwcoKK0=',
			},
			'tvshow': {
				Csfd.TOP100_ALL: 'rlW0rKOyVwbmYPWipzyanJ4vBz51oTjfVzqyoaWyVwcoKFjvrJIupy9zpz9gVwchqJkfYPW5MJSlK3EiVwchqJkfYPWuL3EipvV6J10fVzEcpzIwqT9lVwcoKK0=',
				Csfd.TOP100_CSSK: 'rlW0rKOyVwbmYPWipzyanJ4vBwR5AljvM2IhpzHvBygqYPW5MJSlK2Mlo20vBz51oTjfVayyLKWsqT8vBz51oTjfVzSwqT9lVwcoKFjvMTylMJA0o3VvBygqsD==',
				Csfd.TOP100_CS: 'rlW0rKOyVwbmYPWipzyanJ4vBwRfVzqyoaWyVwcoKFjvrJIupy9zpz9gVwchqJkfYPW5MJSlK3EiVwchqJkfYPWuL3EipvV6J10fVzEcpzIwqT9lVwcoKK0=',
				Csfd.TOP100_SK: 'rlW0rKOyVwbmYPWipzyanJ4vBwVfVzqyoaWyVwcoKFjvrJIupy9zpz9gVwchqJkfYPW5MJSlK3EiVwchqJkfYPWuL3EipvV6J10fVzEcpzIwqT9lVwcoKK0=',
			},
		}
		
		self.cp.log_debug("get_top(%s, %s)" % (media_type, filter_type))
		# dont' check for errors here - we want to know it there is a typo somewhere in code, so here it will crash
		f = filters[media_type][filter_type]

		html = self.call_csfd_api('zebricky/vlastni-vyber', params={'show': 1, 'filter': f})
		vals = []
			
		articles = re.findall('<article.*?href="/film/([0-9]+?)-.*?</article>', html, re.S)
		if articles:
			for article in articles:
				vals.append(article)

		return vals
