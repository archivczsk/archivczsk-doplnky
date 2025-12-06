# -*- coding: utf-8 -*-
import re, json
from tools_archivczsk.contentprovider.provider import CommonContentProvider

__baseurl__ = 'https://tv.idnes.cz/'

class IdnesTvContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None, icons_dir=None):
		CommonContentProvider.__init__(self, 'idnestv', settings=settings, data_dir=data_dir)
		self.req_session = self.get_requests_session()

	def root(self):
		self.add_dir("Vše", None, cmd=self.list_movies, stream = 'webtv')
		self.add_dir("Domácí", None, cmd=self.list_movies, stream = "tv-domaci")
		self.add_dir("Zahraniční", None, cmd=self.list_movies, stream = "tv-zahranicni")
		self.add_dir("Krimi", None, cmd=self.list_movies, stream = "tv-krimi")
		self.add_dir("Sport", None, cmd=self.list_movies, stream = "tv-sport")
		self.add_dir("Technika", None, cmd=self.list_movies, stream = "tv-svet-techniky")
		self.add_dir("Revue", None, cmd=self.list_movies, stream = "tv-spolecnost")
		self.add_dir("Magazíny", None, cmd=self.list_movies, stream = "tv-zivotni-styl")
		self.add_dir("Slow", None, cmd=self.list_movies, stream = "tv-slow")
		self.add_dir("Rozstřel", None, cmd=self.list_movies, stream = "tv-rozstrel")

	def list_movies(self, stream, page=1, **kwargs):
		count = 21
		html = self.req_session.get((__baseurl__ + "data.aspx?type=articlelist-data&strana=" + str(page) + "&version=idn5&section=" + stream + "&klic="))
		videos = html.content.decode('windows-1250').split('<div class="art vgl-art">')[1:]
		for video in videos:
			count -= 1
			match = re.search(r'<a href="(.*?)"', video)
			mainurl = match.group(1) if match else None
			match = re.search(r"background-image:\s*url\('(.*?)'\)", video)
			image = match.group(1) if match else None
			match = re.search(r'<h3>(.*?)</h3>', video)
			title = match.group(1) if match else ""
			match = re.search(r'<span class="time"[^>]*>(.*?)</span>', video)
			date = match.group(1).strip() if match else ""
			match = re.search(r'<span class="length">(.*?)</span>', video)
			length = match.group(1).strip() if match else ""
			match = re.search(r'<video[^>]*data-src="(.*?)"', video)
			preview_url = match.group(1) if match else ""
			video_url = re.sub(r'https://vod.idnes.cz/(.*?)/(.*?)/(.*?)(prev_high)(.*)', r'https://vod.idnes.cz/a/\1/\2/\3flv_high\5', preview_url)
			info_labels = {
				'title': title,
				'plot': date + " - (" + length + ") " + title,
			}
			play_params = {
				'info_labels': info_labels,
			}
			if length == "Živě": # live has a different video url
				m = re.search(r'(V(\d{2})\d+_.*)$', mainurl)
				if m:
					video_id = m.group(1)
					year = "20" + m.group(2)
					html = self.req_session.get("https://1gr.cz/data/nocache/videostream/" + year + "/" + video_id + ".js")
					if html:
						jsondata = json.loads(html.content.decode('windows-1250'))
						if 'video' in jsondata:
							video_url = jsondata['video'][0]['file'];
							self.add_video(title, image, info_labels, cmd=self.get_stream, video_title=title, url=video_url)
						else:
							continue
					else:
						continue
				else:
					continue
			else:
				self.add_video(title, image, info_labels, cmd=self.get_stream, video_title=title, url=video_url)
		if count == 0:
			self.add_next(cmd=self.list_movies, stream=stream, page=int(page)+1, **kwargs)

	def get_stream(self, video_title, url):
		self.add_play(video_title, url)
