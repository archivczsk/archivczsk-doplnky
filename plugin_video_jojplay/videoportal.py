# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.compat import urlparse, parse_qsl
from tools_archivczsk.parser.js import get_js_data
import sys
from tools_archivczsk.cache import ExpiringLRUCache
from Plugins.Extensions.archivCZSK.engine import client

try:
	from bs4 import BeautifulSoup
	bs4_available = True
except:
	bs4_available = False

class JojPlayRedirect(Exception):
	pass

# ##################################################################################################################

class JojVideoportal(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()
		self.req_cache = ExpiringLRUCache(30, 600)

	# ##################################################################################################################

	def _(self, s):
		return self.cp._(s)

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, use_cache=True):
		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = 'https://videoportal.joj.sk/' + endpoint

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
			soup = BeautifulSoup(response.content, "html.parser")

			if use_cache and params == None:
				self.req_cache.put(url, soup)

			return soup
		else:
			raise AddonErrorException(self._('HTTP response code') + ': %d' % response.status_code)

	# ##################################################################################################################

	def root(self):
		if not bs4_available:
			self.cp.show_info(self._("In order addon to work you need to install the BeautifulSoup4 using your package manager. Search for package with name:\npython{0}-beautifulsoup4 or python{0}-bs4)").format('3' if sys.version_info[0] == 3 else ''))
			return

		self.cp.add_dir(self._("TOP shows"), cmd=self.list_category, cat_name='')
		self.cp.add_dir(self._("By alphabet"), cmd=self.list_alphabet)
		self.cp.add_dir(self._("All"), cmd=self.list_category, cat_name='vsetko')

	# ##################################################################################################################

	def list_alphabet(self):
		soup = self.call_api('/relacie')

		for a in soup.find('div', {'class': 'e-az-list' } ).find_all('a'):
			if not a.get('id') and a.get('title') != 'Top':
				self.cp.add_dir(a.get_text(), cmd=self.list_category, cat_name=a.get('href').split('/')[-1] )

	# ##################################################################################################################

	def list_category(self, cat_name):
		if cat_name:
			soup = self.call_api('/relacie/' + cat_name)
		else:
			soup = self.call_api('/relacie')

		for a in soup.find('div', {'class': 's-fullwidth-mobile'}).find_all('a'):
			title = a.find('h3', {'class': 'title'}).get_text().strip()
			img = a.find('img').get('data-original')
			perex_div = a.find('p', {'class': 'perex'})
			info_labels = {
				'plot': perex_div.get_text().strip() if perex_div != None else None
			}
			url = a.get('href')

			if url == 'https://www.joj.sk/jojplay':
				pass
			elif url.startswith('https://videoportal.joj.sk'):
				self.cp.add_dir(title, img, info_labels, cmd=self.check_and_list_show, show_url=url)
			elif url.startswith('https://www.joj.sk/'):
				self.cp.add_dir(title, img, info_labels, cmd=self.list_joj_show, show_url=url)
			else:
				self.cp.log_error("Item %s points to unsupported URL: %s" % (title, url))


	# ##################################################################################################################

	def check_and_list_show(self, show_url):
		# check if we can found this show on JOJ Play and redirect if possible ...
		tag_id = show_url.split('/')[-1]

		data = self.cp.jojplay.client.load_tags_by_id(tag_id)

		if len(data) > 0:
			self.cp.log_debug("Found matching JOJ Play show for tag %s with ref %s" % (tag_id, data[0]['documentId']))
			# found match ... try redirect to JOJ Play
			self.cp.list_tag(data[0]['documentId'])
			if len(client.GItem_lst[0]) > 0:
				# check if there are any episodes in, because some shows are not fully migrated
				return

		self.cp.log_debug("No matching JOJ Play show found for tag %s - continuing to videoportal" % tag_id)
		# not found on JOJ Play - continue to videoportal ...
		return self.list_show(show_url)

	# ##################################################################################################################

	def list_show(self, show_url, season_id=None):
		params = None
		if season_id:
			params = {
				'seasonId': season_id
			}

		try:
			soup = self.call_api(show_url, params=params)
		except JojPlayRedirect as e:
			return self.handle_jojplay_redirect(str(e))

		if season_id == None:
			# search for series a and show list if thare are any
			season_div = soup.find('select', {'onchange': 'return selectSeason(this.value);'})
			if season_div != None:
				for op in season_div.find_all('option'):
					title = op.get_text().strip()
					season_id = op.get('value')

					self.cp.add_dir(title, cmd=self.list_show, show_url=show_url, season_id=season_id)
				return

		for a in soup.find('div', {'class': 'row scroll-item'}).find_all('a'):
			if a.get('href') == '#':
				# ignore next page button - it does nothing ...
				continue

			subtitles = [s.get_text().strip() for s in a.find_all('span', {'class': 'date'})]
			if len(subtitles) > 1:
				title = '{}: {}'.format(subtitles[1], a.find('h3', {'class': 'title'}).get_text().strip())
			else:
				title = a.find('h3', {'class': 'title'}).get_text().strip()

			img = a.find('img').get('data-original')
			info_labels = {
				'plot': subtitles[0] if subtitles else None
			}
			url = a.get('href')

			self.cp.add_video(title, img, info_labels, cmd=self.play_item, item_url=url)

	# ##################################################################################################################

	def list_joj_show(self, show_url):
		soup = self.call_api(show_url)

		subnav_div = soup.find('ul', {'class': 'e-subnav'})

		if subnav_div != None:
			for a in soup.find('ul', {'class': 'e-subnav'}).find_all('a'):
				if a.get('title') == u'Archív':
					url = a.get('href')
					if url.startswith('https://play.joj.sk/'):
						return self.handle_jojplay_redirect(url)
					elif url.startswith('https://videoportal.joj.sk/'):
						return self.list_show(url)
					else:
						self.cp.log_error("Archive of item %s points to unsupported URL: %s" % (show_url, url))
					return

		# direct link to archive not found - try to use tag from URL directly on JOJ Play and see what happens ...
		tag_id = show_url.split('/')[-1]
		data = self.cp.jojplay.client.load_tags_by_id(tag_id)

		if len(data) > 0:
			self.cp.log_debug("Found matching JOJ Play show for tag %s with ref %s" % (tag_id, data[0]['documentId']))
			# found match ... try redirect to JOJ Play
			self.cp.list_tag(data[0]['documentId'])
			if len(client.GItem_lst[0]) > 0:
				# check if there are any episodes in, because some shows are not fully migrated
				return

		# link to archive still not found - try to guess it ...
		try:
			return self.list_show(show_url + '/archiv')
		except:
			self.cp.log_exception()
			try:
				title = soup.find('div', {'class': 's-header'}).find('h2', {'class': 'title'}).find('a').get('title')
			except:
				self.cp.log_exception()
				title = None

			if title:
				# last chance - search for show by its name
				return self.cp.search(title, 'series')

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
					if data[0]['tagTypeRef'].endswith('1X9nXUOc9XbtobIcFdyA'):
						return self.cp.list_tag(tag_id)

		self.cp.show_info(self._("Unsupported JOJ Play redirect type") + ":\n" + url)

	# ##################################################################################################################

	def play_item(self, item_url):
		try:
			soup = self.call_api(item_url)
		except JojPlayRedirect as e:
			return self.handle_jojplay_redirect(str(e), video=True)

		title_div = soup.find('div', {'class': 'b-video-title'}).find('h2')
		try:
			ep_code = title_div.find('span').get_text().strip()
		except:
			ep_code = ''

		title = '{} {}'.format(title_div.get_text().strip()[:-len(ep_code)], ep_code)

		player_url = soup.find('section', {'class' : 's-video-detail'}).find('iframe').get('src')

		soup = self.call_api(player_url)

		# get last script from page
		script = None
		for s in soup.find_all('script'):
			script = s

		play_data = get_js_data(script.string, r'var src = ({.+?});')

		if play_data.get('hls'):
			self.cp.resolve_streams(play_data.get('hls'), title.strip())
		else:
			# HLS not available - try MP4 as fallback ...
			labels = get_js_data(script.string, r'var labels = ({.+?});')

			streams = []
			for i, u in enumerate(play_data.get('mp4', [])):
				q = labels['bitrates']['renditions'][i]
				info_labels = {
					'bandwidth': int(q[:-1]),
					'quality': q
				}

				if self.cp.is_supporter() or info_labels['bandwidth'] <= 720:
					streams.append({
						'url': u,
						'info_labels': info_labels
					})

			for s in sorted(streams, key=lambda x: x['info_labels']['bandwidth'], reverse=True):
				self.cp.add_play(title.strip(), info_labels=s['info_labels'], url=s['url'])


	# ##################################################################################################################
