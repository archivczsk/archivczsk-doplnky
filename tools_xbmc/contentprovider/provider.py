# *		 Copyright (C) 2012 Libor Zoubek
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
from collections import defaultdict
import sys,os,re,traceback

from ..tools import util
from ..resolver import resolver

try:
	from StorageServer import StorageServer
except:
	print( 'Using dummy storage server' )
	from ..tools.storageserverdummy import StorageServer

from Plugins.Extensions.archivCZSK.engine import client

class ResolveException(Exception):
	pass


class ContentProvider(object):
	"""
	ContentProvider class provides an internet content. It should NOT have any xbmc-related imports
	and must be testable without XBMC runtime. This is a basic/dummy implementation.
	"""

	def __init__(self, name='dummy', base_url='/', username=None, password=None, filter=None, tmp_dir='.'):
		"""
		ContentProvider constructor
		Args:
			name (str): name of provider
			base_url (str): base url of site being accessed
			username (str): login username
			password (str): login password
			filter (func{item}): function to filter results returned by search or list methods
			tmp_dir (str): temporary dir where provider can store/cache files
		"""
		self.name = name
		self.username = username
		self.password = password
		if not base_url[-1] == '/':
			base_url += '/'
		self.base_url = base_url
		self.filter = filter
		self.tmp_dir = tmp_dir
		self.cache = StorageServer(self.name, 24)
		self.lang = 'cs' # initialize, current language could be set by XBMContentProvider
		self.silent_mode = False # initialize, current mode will be setby XBMContentProvider

	def __str__(self):
		return 'ContentProvider' + self.name

	def capabilities(self):
		"""
		This way class defines which capabilities it provides ['login','search','resolve','categories']
		It may also contain '!download' when provider does not support downloading
		"""
		return []

	def video_item(self, url='', img='', quality='???'):
		"""
		Returns empty video item - contains all required fields
		"""
		return {'type': 'video', 'title': '', 'rating': 0, 'year': 0, 'size': '0MB', 'url': url, 'img': img,
				'length': '', 'quality': quality, 'subs': '', 'surl': ''}

	def dir_item(self, title='', url='', type='dir'):
		"""
		Returns empty directory item
		"""
		return {'type': type, 'title': title, 'size': '0', 'url': url}

	def login(self):
		"""
		A login method returns True on successfull login, False otherwise
		"""
		return False

	def search(self, keyword):
		"""
		Search for a keyword on a site
		Args:
					keyword (str)

		returns:
			array of video or directory items
		"""
		return []

	def list(self, url):
		"""
		Lists content on given url
		Args:
					url (str): either relative or absolute provider URL

		Returns:
			array of video or directory items

		"""
		return []

	def categories(self):
		"""
		Lists categories on provided site

		Returns:
			array of video or directory items
		"""
		return []

	def findstreams(self, data, regexes=None):
		"""
		Finds streams in given data (see resovler.findstreams for more details)

		:param data: A string (piece of HTML, for example) or an array of URLs
		:param regexes: An array of regexes to be used for extracting URLs from
						'data' of type 'string'
		:returns: An array of video items
		"""
		resolved = resolver.findstreams(data, regexes)
		if resolved is None:
			raise ResolveException(
				'Nelze ziskat video link [CR]zkontrolujte jestli video nebylo odstraneno')
		elif isinstance(resolved, list) and not resolved:
			raise ResolveException('Video je na serveru, ktery neni podporovan')
		elif not resolved:
			raise ResolveException(
				'Nebyl nalezen zadny video embed [CR]zkontrolujte stranku pripadne nahlaste chybu pluginu')
		result = []
		for j in resolved:
			i = defaultdict(lambda: '', j)
			item = self.video_item()
			item['title'] = i['name']
			item['url'] = i['url']
			item['quality'] = i['quality']
			item['surl'] = i['surl']
			item['subs'] = i['subs']
			item['headers'] = i['headers']
			item['lang'] = i['lang']
			item['info'] = i['info']
			result.append(item)
		return result

	def resolve(self, item, captcha_cb=None, select_cb=None, wait_cb=None):
		"""
		Resolves given video item  to a downloable/playable file/stream URL

		Args:
			url (str): relative or absolute URL to be resolved
			captcha_cb(func{obj}): callback function when user input is required (captcha, one-time passwords etc).
			function implementation must be Provider-specific
			select_cb(func{array}): callback function for cases when given url resolves to multiple streams,
			provider class may call this function and require user interaction
			wait_cb(func{obj}): callback function for cases when url resolves to stream which becomes available
			somewhere in future (typically in several seconds). Provider may call this and require waiting.
		Returns:
			None - if ``url`` was not resolved. Video item with 'url' key pointing to resolved target
		"""
		return None

	def _url(self, url):
		"""
		Transforms relative to absolute url based on ``base_url`` class property
		"""
		if url.startswith('http'):
			return url
		return self.base_url + url.lstrip('./')

	def _filter(self, result, item):
		"""
		Applies filter, if filter passes `item` is appended to `result`

		Args:
			result (array) : target array
			item (obj) : item that is being applied filter on
		"""
		if self.filter:
			if self.filter(item):
				result.append(item)
		else:
			result.append(item)

	def debug(self, msg):
		client.log.debug('[%s] %s' % (self.name, msg))

	def info(self, msg):
		client.log.info('[%s] %s' % (self.name, msg))

	def error(self, msg):
		client.log.error('[%s] %s' % (self.name, msg))

	def stats(self, item, action):
		"""
		Lists content on given url
		Args:
					item

		Returns:
			nothing

		"""
		pass
	
	def stats_ext(self, item, action, extra_params):
		"""
		Lists content on given url
		Args:
					item

		Returns:
			nothing

		"""
		pass
	
	def trakt(self, item, action, result, msg):
		"""
		make some action with trakt.tv
		Args:
					item

		Returns:
			nothing

		"""
		return None


class cached(object):
	"""
	A method decorator that can be used on any ContentProvider method
	Having this decorator means that results of such method are going
	to be cached for 24hours by default. You can pass number argument
	to decorator, for example @cached(1) would cache for 1 hour.
	"""

	def __init__(self, ttl=24):
		self.ttl = ttl

	def __call__(self, f):
		def wrap(*args):
			provider = args[0]
			cache = StorageServer(provider.name + str(self.ttl), self.ttl)
			return cache.cacheFunction(f, *args)

		return wrap
