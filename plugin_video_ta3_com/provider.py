# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
import sys

try:
	from bs4 import BeautifulSoup
	bs4_available = True
except:
	bs4_available = False

class Ta3ContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None):
		CommonContentProvider.__init__(self, 'TA3', settings=settings, data_dir=data_dir)
		self.ta3 = None

	# ##################################################################################################################

	def root(self):
		if not bs4_available:
			self.show_info(self._("In order addon to work you need to install the BeautifulSoup4 using your package manager. Search for package with name:\npython{0}-beautifulsoup4 or python{0}-bs4)").format('3' if sys.version_info[0] == 3 else ''))
			return

		if self.ta3 == None:
			from .ta3 import TA3
			self.ta3 = TA3(self)

		self.add_video('TA3 Live', cmd=self.resolve_live_video, video_title="TA3 Live", section='live', download=False)
		self.add_video('NRSR Live', cmd=self.resolve_live_video, video_title="NRSR Live", section='nrsr', download=False)

		self.add_dir(self._("Archive of programs"), cmd=self.list_archive)
		self.add_dir(self._("Slovakia"), cmd=self.list_articles, section="slovensko")
		self.add_dir(self._("Foreign"), cmd=self.list_articles, section="zahranicie")
		self.add_dir(self._("Economics"), cmd=self.list_articles, section="ekonomika")
		self.add_dir(self._("Regions"), cmd=self.list_articles, section="regiony")
		self.add_dir(self._("Sport"), cmd=self.list_articles, section="sport")
		self.add_dir(self._("Press conferences"), cmd=self.list_articles, section="tlacove-besedy")
		self.add_dir(self._("Society"), cmd=self.list_articles, section="spolocnost")
		self.add_dir(self._("Auto-moto"), cmd=self.list_articles, section="auto-moto")
		self.add_dir(self._("Health"), cmd=self.list_articles, section="zdravie")
		self.add_dir('новини', cmd=self.list_articles, section="ukrajinski-novyny")

	# ##################################################################################################################

	def safe_call(self, cmd, *args, **kwargs):
		try:
			ret = cmd(*args, **kwargs)
		except:
			self.log_exception()
			self.show_error(self._("Error extracting data from ta3.com. Format of the site is probably changed and addon needs to be modified in order to work again. Please report this problem to addon authors."))
			ret = None

		return ret

	# ##################################################################################################################

	def list_articles(self, section, page=1):
		articles, max_page = self.safe_call(self.ta3.get_articles, section, page)

		self.log_debug("Adding %s" % str(articles))
		for p in articles:
			info_labels = {
				'plot': p['desc']
			}
			self.add_video(p['name'], p['img'], info_labels, cmd=self.resolve_video, url=p['url'])

		if max_page != None and page < max_page:
			self.add_next(page_info=(page+1, max_page), cmd=self.list_articles, section=section, page=page+1)

	# ##################################################################################################################

	def list_archive(self):
		for p in self.safe_call(self.ta3.get_programs):
			info_labels = {
				'plot': p['desc']
			}
			self.add_dir(p['name'], p['img'], info_labels, cmd=self.list_episodes, url=p['url'])

	# ##################################################################################################################

	def list_episodes(self, url, page=1):
		episodes, max_page = self.safe_call(self.ta3.get_episodes, url, page)

		for e in episodes:
			info_labels = {
				'plot': e['desc']
			}
			self.add_video(e['name'], e['img'], info_labels, cmd=self.resolve_video, url=e['url'])

		if max_page != None and page < max_page:
			self.add_next(page_info=(page+1, max_page), cmd=self.list_episodes, url=url, page=page+1)

	# ##################################################################################################################

	def resolve_streams(self, url, video_title):
		for one in self.get_hls_streams(url, self.ta3.req_session):
			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('resolution', 'x???').split('x')[1] + 'p'
			}
			self.add_play(video_title, one['url'], info_labels=info_labels)

	# ##################################################################################################################

	def resolve_video(self, url):
		video_url, title = self.safe_call(self.ta3.get_video_url, url)
		self.resolve_streams(video_url, title)

	# ##################################################################################################################

	def resolve_live_video(self, section, video_title):
		video_url = self.safe_call(self.ta3.get_live_video_url, section)
		self.resolve_streams(video_url, video_title)

	# ##################################################################################################################
