# -*- coding: UTF-8 -*-
# /*
# *		 Copyright (C) 2013 Maros Ondrasek
# *
# *
# *	 This Program is free software; you can redistribute it and/or modify
# *	 it under the terms of the GNU General Public License as published by
# *	 the Free Software Foundation; either version 2, or (at your option)
# *	 any later version.
# *
# *	 This Program is distributed in the hope that it will be useful,
# *	 but WITHOUT ANY WARRANTY; without even the implied warranty of
# *	 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *	 GNU General Public License for more details.
# *
# *	 You should have received a copy of the GNU General Public License
# *	 along with this program; see the file COPYING.	 If not, write to
# *	 the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *	 http://www.gnu.org/copyleft/gpl.html
# *
# */

import re
import random
from xml.etree.ElementTree import fromstring
from Plugins.Extensions.archivCZSK.engine import client

from tools_xbmc.tools import util
from tools_xbmc.contentprovider.provider import ContentProvider
try:
	from urllib2 import urlopen, HTTPCookieProcessor, build_opener, install_opener
	from urlparse import urlparse
	import cookielib
except:
	from urllib.request import urlopen, HTTPCookieProcessor, build_opener, install_opener
	from urllib.parse import urlparse
	import http.cookiejar as cookielib

BASE_URL = {"JOJ": "https://www.joj.sk",
			"JOJ Plus": "http://plus.joj.sk",
			"WAU": "http://wau.joj.sk"}

LIVE_URL = {"JOJ": "http://joj.sk",
			"JOJ Plus": "http://plus.joj.sk",
			"WAU": "http://wau.joj.sk",
			"JOJ24": "https://joj24.noviny.sk/"}

JOJ_NAMES = {'JOJ': 'JOJ',
			'JOJ Plus': 'PLUS',
			'WAU': 'WAU',
			'JOJ24': 'JOJ24'}


class JojContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, filter=None):
		ContentProvider.__init__(self, 'joj.sk', 'http://www.joj.sk/', username, password, filter)
		opener = build_opener(HTTPCookieProcessor(cookielib.LWPCookieJar()))
		install_opener(opener)
		self.debugging = False

	def debug(self, text):
		if self.debugging:
			print("[DEBUG][%s] %s" % (self.name, text))

	def capabilities(self):
		return ['categories', 'resolve', '!download']

	def _fix_url(self, url):
		if url.startswith('//'):
			url = 'http:' + url
		return url

	def _fix_url_next(self, url_old, url_new):
		url_new = self._fix_url(url_new)
		first_part = url_old.split('?')[0]
		second_part = url_new.split('?')[1].replace('&amp;', '&')
		return first_part + '?' + second_part

	def _list_article(self, data):
		url_and_title_match = re.search(r'<a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)"', data)
		if url_and_title_match is None:
			return None
		item = {}
		item['title'] = url_and_title_match.group('title')
		#print('title = ', item['title'])
		item['url'] = self._fix_url(url_and_title_match.group('url'))
		#print('url = ', item['url'])
		subtitle_match = re.search(r'<h4 class="subtitle">.+?<span class="date">([^<]+)',
								   data, re.DOTALL)
		if subtitle_match:
			item['subtitle'] = subtitle_match.group(1)
		episodenum_match = re.search(r"""<h4\ class="subtitle">.+?<div\ class="col\ text-right">
									  <span\ class="date">([^<]+)""",
									  data, re.DOTALL | re.VERBOSE)
		if episodenum_match:
			item['episodenum'] = episodenum_match.group(1)
		img_match = re.search(r'<img\s+[^>]+data-original="([^"]+)"', data)
		if img_match:
			item['img'] = self._fix_url(img_match.group(1))
		return item

	def _list_archive(self, data):
		# url_and_title_match = re.search(r'<a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)"', data)
		url_and_title_match = re.search(r'<a href="(?P<url>[^"]+)".*?title="(?P<title>[^"]+)".*?<img\s+[^>]+data-original="(?P<img>[^"]+)".*?<article.*?<a href="(?P<url2>[^"]+)"', data, re.S)
		if url_and_title_match is None:
			return None
		item = {}
		item['title'] = url_and_title_match.group('title')
		#print('title = ', item['title'])
		item['url'] = self._fix_url(url_and_title_match.group('url2'))
		#print('url = ', item['url'])
		subtitle_match = re.search(r'<h4 class="subtitle">.+?<span class="date">([^<]+)',
								   data, re.DOTALL)
		if subtitle_match:
			item['subtitle'] = subtitle_match.group(1)
		episodenum_match = re.search(r"""<h4\ class="subtitle">.+?<div\ class="col\ text-right">
									  <span\ class="date">([^<]+)""",
									  data, re.DOTALL | re.VERBOSE)
		if episodenum_match:
			item['episodenum'] = episodenum_match.group(1)
		# img_match = re.search(r'<img\s+[^>]+data-original="([^"]+)"', data)
		# if img_match:
			# item['img'] = self._fix_url(img_match.group(1))
		img = self._fix_url(url_and_title_match.group('img'))
		img = re.sub('r100x100', 'r600x340n', img)	#zvysenie kvality obrazka z 100px na 600px
		item['img'] = img
		return item

	def list_base(self, url):
		result = []
		self.info("list_base %s" % url)
		data = util.request(url)
		# data = util.substr(data, '<section class="s s-container s-videozone s-archive s-tv-archive">', '<div class="s-footer-wrap">')
		data = util.substr(data, '<section class="s s-container s-videozone s-archive-content">', '<div class="s-footer-wrap">')
		# for article_match in re.finditer('<article class="b-article article-md media-on">(.+?)</article>', data, re.DOTALL):
		# for article_match in re.finditer('<div class="col-xs-12 col-md-3 w-title">(.+?)</div>', data, re.DOTALL):
		for article_match in re.finditer('<div class="col-xs-12 col-md-3 w-title">(.+?)</article>', data, re.DOTALL):
			article_dict = self._list_archive(article_match.group(1))
			if article_dict is not None:
				item = self.dir_item()
				item.update(article_dict)
				item['url'] = '/'.join(item['url'].split('/')[:-2]) + "#s"
				result.append(item)
		return result

	def list_show(self, url, list_series=False, list_episodes=False):
		result = []
		self.info("list_show %s" % (url))
		# print('list_series: %s' % list_series)
		# print('list_episodes: %s' % list_episodes)
		# print ('url=', url)
		data = util.request(url)
		if list_series:
			series_data = util.substr(data, r'<select onchange="return selectSeason(this.value);">', '</select>')
			for serie_match in re.finditer(r'<option value="(?P<season_id>\d+)?"\s(selected="selected")?>\s+(?P<title>[^<]+)\n', series_data):
				item = self.dir_item()
				season_id = serie_match.group('season_id')
				if not season_id:
					season_id = ""
				item['title'] = serie_match.group('title')
				# item_title = serie_match.group('title')

				item['url'] = "%s?seasonId=%s" % (url.split('#')[0], season_id)
				result.append(item)

			# check related clips on joj.sk
			try:
				joj_data = util.request(url.replace('https://videoportal.joj.sk', 'https://joj.sk'))
			except:
				joj_data = util.request(url)
			try:
				d_joj_data = joj_data.decode("utf-8")
			except:
				d_joj_data = joj_data
			menu_data = util.substr(d_joj_data, r'ul class="e-subnav">', '</ul')
			for menu_item in re.finditer(r'<a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)"', menu_data):
				item = self.dir_item()
				item['title'] = menu_item.group('title')
				# item_title = menu_item.group('title')
				item['url'] = menu_item.group('url')
				result.append(item)

		if list_episodes:
			episodes_data = data
			# clips on joj.sk
			it1 = re.finditer(r'<article class="b-article article-md media-on">(.+?)</article>',
							  data,
							  re.DOTALL)
			# videos on videoportal.joj.sk
			it2 = re.finditer(r'<article class="b-article title-xs article-lp">(.+?)</article>',
							  data,
							  re.DOTALL)
			for article_match in list(it1) + list(it2):
				article_dict = self._list_article(article_match.group(1))
				if article_dict is not None:
					item = self.video_item()
					item.update(article_dict)
					# item['title'] += ' ' + item.get('subtitle', '')
					# item['title'] += ' [COLOR FFB2D4F5]%s[/COLOR]'%item.get('subtitle', '')
					item_subtitle = item.get('subtitle', '')
					if 'episodenum' in item.keys():
						# item['title'] += '/' + item.get('episodenum', '')
						# item['title'] += ' | ' + item.get('episodenum', '')
						item_episode = item.get('episodenum', '')
						t = re.search('([\d]{1,})', item_episode)
						if t:
							item_episode = int(t.group(1))

						# item_subtitle =item.get('episodenum', '')
						t = re.search('([\d]{1,})\. ?([\d]{1,2})\. ?([\d]{4})', item_subtitle)
						if t:
							d, m, y = int(t.group(1)), int(t.group(2)), int(t.group(3))
							item_subtitle = '{:02d}.{:02d}.{}'.format(d, m, y)

						item['title'] = 'Epizóda {:02d}: [COLOR FFFFAA00]{}[/COLOR] | [COLOR FFB2D4F5]{}[/COLOR]'.format(item_episode, item['title'], item_subtitle)
						result.append(item)
			title_to_key = {
				'Dátum':'date',
				'Názov epizódy':'title',
				'Sledovanosť':'seen',
				'Séria':'season',
				'Epizóda':'episode'}
			headers_match = re.search('<div class="i head e-video-categories">(.+?)</div>', episodes_data, re.DOTALL)
			if headers_match is not None:
				headers = []
				for span_match in re.finditer('<span[^>]*>([^<]+)</span>', headers_match.group(1)):
					key = title_to_key.get(span_match.group(1))
					if key is None:
						print("undefined key", span_match.group(1))
						headers.append("")
					else:
						headers.append(key)
				archive_list_pattern = r'<a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)[^>]+>\s+'
				for key in headers:
					if key in ("", "title"):
						archive_list_pattern += r'^.+?$\s+'
					else:
						archive_list_pattern += r'<span>(?P<%s>[^<]*)</span>\s+' % key
				for archive_list_match in re.finditer(archive_list_pattern, episodes_data, re.MULTILINE):
					item = self.video_item()
					groupdict = archive_list_match.groupdict()
					# print (archive_list_match)
					if 'season' in groupdict and 'episode' in groupdict:
						# joj sometimes don't provide season/episode numbers
						# for latest episodes, so mark them as 0.
						try:
							season = int(archive_list_match.group('season'))
						except Exception:
							season = 0
						try:
							episode = int(archive_list_match.group('episode'))
						except Exception:
							episode = 0
						item['title'] = "(S%02d E%02d) - %s" % (season, episode,
															  archive_list_match.group('title'))
					else:
						item['title'] = ">>>(%s) - %s" % (archive_list_match.group('date'),
													 archive_list_match.group('title'))
					item['url'] = self._fix_url(archive_list_match.group('url'))
					result.append(item)
			'''
			if url.find('-page=') > 0 and url.find('-listing') > 0:
				pagination_data = data
			else:
				pagination_data = util.substr(data, r'<section>', '</section>')
			'''
			pagination_data = data
			# match on videoportal.joj.sk site
			next_match = re.search(r'a.*data-href="(?P<url>[^"]+)".*title="Načítaj viac"', pagination_data, re.DOTALL)
			if next_match:
				item = self.dir_item()
				item['type'] = 'next'
				item['url'] = self._fix_url_next(url, next_match.group(1))
				result.append(item)
			# match on joj.sk site
			# print(pagination_data)
			next_match = re.search(r'a href="(?P<url>[^"]+)" aria-label="Ďalej"', pagination_data, re.DOTALL)
			if next_match:
				item = self.dir_item()
				item['type'] = 'next'
				item['url'] = next_match.group('url')
				result.append(item)
		return result

	def list(self, url):
		self.info("list %s" % url)
		# print ('list url', url)
		url_parsed = urlparse(url)
		if not url_parsed.path:
			if url not in BASE_URL.values():
				print("not joj.sk url!")
				return []
			return self.subcategories(url)
		if url_parsed.fragment == "s":
			result = self.list_show(url, list_episodes=True, list_series=True)
			return result
		return self.list_show(url, list_episodes=True)

	def categories(self):
		result = []
		data = self.liveInfo()
		for k, v in LIVE_URL.items():
			item = self.video_item()
			item['title'] = k + ' (LIVE)'
			item['url'] = v + '/live.html'

			if k in JOJ_NAMES:
				kk = JOJ_NAMES[k]
				if kk:
					item['plot'] = data[kk]['desc']
					item['img'] = data[kk]['img']
			result.append(item)
		result.append(self.dir_item("JOJ archív", BASE_URL["JOJ"]))
		result.append(self.dir_item("JOJ Plus archív", BASE_URL["JOJ Plus"]))
		result.append(self.dir_item("WAU archív", BASE_URL["WAU"]))
		return result

	def subcategories(self, base_url):
		# return self.list_base(base_url + '/archiv-filter')
		return self.list_base(base_url + '/archiv')

	def removeTags(self, text):
			text = re.sub('<.*?>', '', text)
			text = re.sub('[\r\n\t\0]', '', text)
			text = re.sub('^[ ]+|[ ]+$', '', text)
			return text

	def liveInfo(self):
		data_new = {}
		url = 'https://live.joj.sk/'
		data = util.request(url)
		s = re.finditer(' <div class="col-xs-12 col-sm-6 col-md-4 i h-.">(?P<data>.*?<\/div>)[ \n]+<\/div>[ \n]+<\/div>', data, re.S)
		if s:
			for ss in s:
				d = ss.group('data')
				img, title, time = None, None, None
				a = re.search('title="(?P<title>.*?)" .*?<img src="(?P<img>.*?)"', d, re.S)
				if a:
					img, title = a.group('img'), a.group('title')

				a = re.finditer('<h3 class="title">(?P<title>.*?)<\/h3>.*?<div class="time">(?P<time>.*?)<\/div>', d, re.S)
				desc = ''
				if a:
					for aa in a:
						desc += '%s: %s\n' % (aa.group('time'), self.removeTags(aa.group('title')))
				data_new[title] = {'img': img, 'title': title, 'desc': desc}

		img_joj24 = 'https://img.joj.sk/rx240/38a52c95-84ce-4c04-b70a-2289a9fd1541'
		title = 'JOJ24'
		data_new[title] = {'img': img_joj24, 'title': title, 'desc': ''}

		return data_new

	def resolve(self, item, captcha_cb=None, select_cb=None):
		result = []
		item = item.copy()
		url = item['url']
		if url.endswith('live.html'):
			channel = urlparse(url).netloc.split('.')[0]
			sou = 'hls'
			if channel in 'plus':
				channel = 'jojplus'
			if channel == 'joj24':
				channel = 'joj_news'
				sou = 'andromeda'
			channel_quality_map = {'joj': ('360', '540', '720'),
								   'jojplus': ('360', '540'),
								   'wau': ('360', '540'),
								   'joj_news': ('404', '720', '1080')
								   }
			for quality in channel_quality_map[channel]:
				item = self.video_item()
				item['quality'] = quality + 'p'
				item['url'] = 'https://live.cdn.joj.sk/live/' + sou + '/' + channel + '-' + quality + '.m3u8'
				result.append(item)
		else:
			data = util.request(url)
			vdata = util.substr(data, '<section class="s-section py-0 s-video-detail">', '</section>')
			# maybe this is video on joj.sk (not on videoportal.joj.sk)?
			if not vdata:
				vdata = util.substr(data, '<div class="b-article-video">', '</div>')
			# .. still joj.sk but different format
			if not vdata:
				vdata = util.substr(data, '<div class="intro">', '</div>')
			if not vdata:
				vdata = util.substr(data, '<div style="position:relative !important;', '</div>')
			iframe_url = re.search('<iframe src="([^"]+)"', vdata).group(1)
			#print('iframe_url = ', iframe_url)
			player_str = urlopen(iframe_url).read()
			#print(player_str)
			d_player_str = player_str.decode("utf-8")

			labels_str = re.search(r'var labels = {(.+?)};', d_player_str, re.DOTALL).group(1)
			#print('labels:', labels_str)
			renditions = re.search(r'renditions: \[(.+?)\]', labels_str).group(1).replace("'", "").replace('"', '').split(',')
			#print('renditions: ', renditions)

			settings_str = re.search(r'var settings = {(.+?)};', d_player_str, re.DOTALL).group(1)
			#print('settings:', settings_str)
			poster_url = re.search(r'poster: \[\"(.+?)\"[^\]]*\]', settings_str).group(1)
			#print('poster_url:', poster_url)

			bitrates_str = re.search(r'var src = {(.+?)};', d_player_str, re.DOTALL).group(1)
			#print('bitrates:', bitrates_str)
			bitrates_url = re.search(r'"mp4": \[(.+?)\]', bitrates_str, re.DOTALL).group(1)
			bitrates_url = bitrates_url.replace("'", "").replace('\n', '').replace(' ', '').split(',')
			for idx, url in enumerate(bitrates_url):
				item = self.video_item()
				item['img'] = poster_url
				item['quality'] = renditions[idx]
				item['url'] = url
				result.append(item)
		result.reverse()
		if select_cb:
			return select_cb(result)
		return result

