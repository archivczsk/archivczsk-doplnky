# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.string_utils import _I, _C, _B
from tools_archivczsk.date_utils import iso8601_to_datetime
from tools_archivczsk.string_utils import clean_html
from tools_archivczsk.compat import urljoin, quote
from datetime import datetime, date, timedelta
from functools import partial
import time, string
import re

class TvNoeModuleLiveTV(CPModuleLiveTV):
	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider)

	# #################################################################################################

	def load_current_epg(self):
		data = self.cp.call_json_api('program')

		now = datetime.now()
		ret = {}

		for channel, program in data.get('program', {}).items():
			last_program = {}
			for p in program:
				d = iso8601_to_datetime(p['zacatek'])
				if now < d:
					break

				last_program = {
					'title': '{}: {}'.format(p['nazev'], p['podnazev']) if p.get('podnazev') else p['nazev'],
					'img': p['imgUrl'],
					'plot': p['popis'],
					'start': d
				}

			ret[channel] = last_program

		return ret


	# #################################################################################################

	def get_live_tv_channels(self):
		data = self.cp.call_json_api('live')

		epg_data = self.load_current_epg()

		logo_data = {}
		for k in sorted(data.get('logo',{}).keys(), reverse=True):
			logo_data = data['logo'][k]
			break

		for name, url in data.get('stream', {}).items():
			epg = epg_data.get(name)

			if epg:
				info_labels = {
					'title': epg['title'],
					'plot': '[{}]\n{}'.format(epg['start'], clean_html(epg['plot']).strip())
				}
				epg_str = ' ' + _I(epg['title'])
			else:
				epg_str = ""
				info_labels = None

			self.cp.add_video(name + epg_str, epg.get('img') or logo_data.get(name), info_labels, cmd=self.get_livetv_stream, channel_name=name, url=url)

	# #################################################################################################

	def get_livetv_stream(self, channel_name, url):
		self.cp.resolve_hls_streams(channel_name, url)


# #################################################################################################

class TvNoeModuleArchive(CPModuleArchive):
	def __init__(self, content_provider):
		CPModuleArchive.__init__(self, content_provider, name=content_provider._("Schedule"))

	# #################################################################################################

	def get_archive_channels(self):
		data = self.cp.call_json_api('live')

		logo_data = {}
		for k in sorted(data.get('logo',{}).keys(), reverse=True):
			logo_data = data['logo'][k]
			break

		for name in data.get('stream', {}).keys():
			self.add_archive_channel(name, name, 21*24, img=logo_data.get(name), show_archive_len=False)


	# #################################################################################################

	def show_future_days(self, channel_id):
		for i in range(14, 1, -1):
			if i == 1:
				day = date.today() + timedelta(days=i)
				day_name = self._("Tomorrow") + ' ' + day.strftime("%d.%m.%Y")
			else:
				day = date.today() + timedelta(days=i)
				day_name = self._(self.days_of_week[day.weekday()]) + " " + day.strftime("%d.%m.%Y")

			self.cp.add_dir(day_name, cmd=self.get_archive_program, channel_id=channel_id, archive_day=-i)

	# #################################################################################################

	def get_archive_days_for_channels(self, channel_id, archive_hours, page=0):
		if page == 0:
			self.show_future_days(channel_id)

		return super(TvNoeModuleArchive, self).get_archive_days_for_channels(channel_id, archive_hours, page)

	# #################################################################################################

	def get_channel_epg(self, channel_id, date_str):
		data = self.cp.call_json_api('program/' + date_str)
		ret = []

		for channel, program in data.get('program', {}).items():
			if channel != channel_id:
				continue

			for p in program:
				ret.append({
					'title': '{}: {}'.format(p['nazev'], p['podnazev']) if p.get('podnazev') else p['nazev'],
					'img': p['imgUrl'],
					'plot': clean_html(p['popis']).strip(),
					'start': iso8601_to_datetime(p['zacatek']),
					'url': p.get('videoUrl'),
				})

		return ret

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		date_from, date_to = self.archive_day_to_datetime_range(archive_day)
		now = datetime.now()

		# store live stream urls - needed to construct DVR urls later
		data = self.cp.call_json_api('live')
		live_url = {}
		for name, url in data.get('stream', {}).items():
			live_url[name] = url


		epg_data = self.get_channel_epg(channel_id, str(date_from.date()))
		for i, epg in enumerate(epg_data):
			if epg['url'] or (epg['start'] < now and epg['start'] > (now - timedelta(hours=24*7))):
				title = '%s - %s' % (epg["start"].strftime("%H:%M"), _I(epg["title"]))

				if not epg['url']:
					# we don't have direct show url, so create DVR url as a replacement for missing video url
					ts = int(time.mktime(epg['start'].timetuple()))
					try:
						duration = int((epg_data[i+1]['start'] - epg['start']).total_seconds())
					except:
						duration = 7200

					epg['url'] = urljoin(live_url[channel_id], 'playlist_dvr_range-{}-{}.m3u8'.format(ts-60, duration + 360))

			else:
				title = _C('gray', '%s - %s' % (epg["start"].strftime("%H:%M"), epg["title"]))

			info_labels = {
				'plot': epg['plot'],
				'title': epg["title"]
			}

			self.cp.add_video(title, epg['img'], info_labels, cmd=self.get_archive_stream, archive_title=str(epg["title"]), video_url=epg['url'])

	# #################################################################################################

	def get_archive_stream(self, archive_title, video_url):
		if not video_url:
			return

		return self.cp.resolve_hls_streams(archive_title, video_url)


# #################################################################################################


class TvNoeModuleVideoLibrary(CPModuleTemplate):
	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("Video library"))

	# #################################################################################################

	def root(self):
		for l in string.ascii_uppercase:
			self.cp.add_dir(l, cmd=self.list_letter, letter=l)

	# #################################################################################################

	def list_letter(self, letter):
		soup = self.cp.call_web_api('videoteka/az/'+ letter.lower())
		titles = []

		for div in soup.find_all("div", class_="noe-porady-prehled-porad"):
			title = div.find("div", style="display:block; width: 100%;color: #424753;font-weight: bold;").text.split(":")[0].strip()
			if title not in titles:
				titles.append(title)
			else:
				continue

			img = urljoin('https://www.tvnoe.cz/', div.find('img')['src'])
			self.cp.add_dir(title, img, cmd=self.list_episodes, url='videoteka/hledej?search=' + quote(title.encode('utf-8')))

	# #################################################################################################

	def list_episodes(self, url):
		soup = self.cp.call_web_api(url)

		for a in soup.find("div", class_="noe-videoteka-prehled-porady").find_all('a'):
			title = a.find("div", style="display:block; width: 100%;color: #424753;font-weight: bold;").text.strip()
			img = urljoin('https://www.tvnoe.cz/', a.find('img')['src'])
			info_labels = partial(self.load_info_labels, url=a['href'])
			self.cp.add_video(title, img, info_labels, cmd=self.resolve_episode_video, video_title=title, url=a['href'])

	# #################################################################################################

	def resolve_episode_video(self, video_title, url):
		soup = self.cp.call_web_api(url)
		h = soup.find("div", class_="container craplayer").decode_contents()
		video_url = re.compile(r"src:\s*'([^']*\.m3u8)'").findall(h)[0]

		return self.cp.resolve_hls_streams(video_title, video_url)

	# #################################################################################################

	def load_info_labels(self, url):
		plot = ''
		if url.startswith('/porad/'):
			self.cp.log_debug("Resolving info data using API")
			id_kat = url[7:].split('-')[0]
			data = self.cp.call_json_api('detail/' + id_kat)
			plot = clean_html((data or [{}])[0].get('popis','')).strip()

		if not plot:
			self.cp.log_debug("Resolving info data using web")
			soup = self.cp.call_web_api(url)

			for x in soup.find('div', class_='col'):
				if x.name == 'p' and x.text:
					plot = x.text.strip()
					break

		return {
			'plot': plot
		}

# #################################################################################################

class TvNoeContentProvider(ModuleContentProvider):

	def __init__(self):
		ModuleContentProvider.__init__(self)

		self.req_session = self.get_requests_session()
		self.beautifulsoup = self.get_beautifulsoup()

		self.modules = [
			TvNoeModuleLiveTV(self),
			TvNoeModuleArchive(self),
			TvNoeModuleVideoLibrary(self)
		]

	# #################################################################################################

	def login(self, silent):
		return True

	# #################################################################################################

	def call_json_api(self, endpoint):
		url = 'https://api.tvnoe.cz/' + endpoint
		response = self.req_session.get(url)
		response.raise_for_status()

		return response.json()

	# #################################################################################################

	def call_web_api(self, url):
		response = self.req_session.get(urljoin('https://www.tvnoe.cz/', url))
		self.log_debug("Requesting URL: %s" % response.request.url)
		response.raise_for_status()

		return self.beautifulsoup(response.content, 'html.parser')

	# #################################################################################################

	def get_hls_info(self, stream_key):
		resp = {
			'url': stream_key['url'],
			'bandwidth': stream_key['bandwidth'],
		}

		return resp

	# #################################################################################################

	def resolve_hls_streams(self, title, playlist_url):
		for p in self.get_hls_streams(playlist_url, self.req_session):
			bandwidth = int(p['bandwidth'])

			info_labels = {
				'quality': p.get('resolution', 'x720').split('x')[1] + 'p',
				'bandwidth': bandwidth
			}

			self.add_play(title, stream_key_to_hls_url( self.http_endpoint, {'url': p['playlist_url'], 'bandwidth': p['bandwidth']}), info_labels)

	# #################################################################################################
