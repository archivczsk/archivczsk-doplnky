import re,sys,os,time,requests,traceback,random

try:
	sys.path.append( os.path.dirname(__file__) )
except:
	pass

import threading, json
from datetime import date, timedelta, datetime
from Plugins.Extensions.archivCZSK.engine import client

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

from sc_cache import ExpiringLRUCache
import util
from provider import ContentProvider
from kraska import Kraska
from sc_webshare import Webshare

try:
	from urlparse import urlparse, urlunparse, parse_qsl
	from urllib import quote, urlencode
except:
	from urllib.parse import quote, urlparse, urlunparse, urlencode, parse_qsl

# #################################################################################################

# disabled, because images doesn't look very good on enigma2 skins
_KODI_IMG_MAP = {
#	'defaultmovies.png': 'DefaultMovies.png',
#	'defaulttvshows.png': 'DefaultTVShows.png',
#	'defaultmusicvideos.png': 'DefaultMusicVideos.png',
#	'defaultaddonpvrclient.png': 'DefaultAddonPVRClient.png',
}

_KODI_IMG_URL='https://github.com/xbmc/skin.confluence/raw/master/media/'

_MATURITY_RATING_MAP = {
	"0": -1,
	"1": 0,
	"2": 6,
	"3": 12,
	"4": 15,
	"5": 18,
}

# these methods are supported by SC
_KODI_SORT_METHODS = {
	39: (None, "Predvolené"), 
	19: ('rating', "Hodnotenie"), # works ok
	30: ('mpaa', "Prístupnosť"), # No idea if it works ok
	36: ('title', "Titul"), # wtf???
	26: ('name', "Meno"), # results are funny ...
	18: ('year', "Rok"), # works ok
	21: ('datum', "Dátumu pridania"), # works ok?
}

API_VERSION='2.0'

addon = ArchivCZSK.get_xbmc_addon('plugin.video.stream-cinema')

# #################################################################################################

class SCWatched:
	
	# #################################################################################################
	
	def __init__(self, data_dir, max_items=50 ):
		self.max_items = max_items
		self.data_dir = data_dir
		self.watched_file = os.path.join( self.data_dir, "watched.json" )
		self.need_save = False
		self.items = {}
		self.load()
	
	# #################################################################################################
	
	def clean(self):
		lp = self.items.get( 'last_played_position' )
		if lp and len( lp ) > self.max_items:
			# sort last played items by time added and remove oldest over max items
			lp = [ x[0] for x in sorted( lp.items(), key=lambda x: -x[1]['time']) ][self.max_items:]
			self.need_save = True
		
		for wtype in self.items:
			if wtype == 'last_played_position':
				continue
			if len( self.items[wtype] ) > self.max_items:
				self.items[wtype] = self.items[wtype][:self.max_items]
				self.need_save = True
		
	# #################################################################################################
	
	def load(self):
		try:
			with open( self.watched_file, "r" ) as f:
				self.items = json.load(f)
				
			self.clean()
		except:
			pass

		# #################################################################################################

	def save(self):
		if self.need_save:
			with open( self.watched_file, "w" ) as f:
				json.dump(self.items, f)
				
			self.need_save = False
			
	# #################################################################################################
	
	def get(self, wtype):
		return self.items.get(wtype, [])
	
	# #################################################################################################

	def set(self, wtype, data):
		if self.max_items > 0:
			if wtype not in self.items:
				self.items[wtype] = []
			
			self.remove( wtype, data['url'] )
			self.items[wtype].insert(0, data )
			
			if len(self.items[wtype]) > self.max_items:
				self.items[wtype] = self.items[wtype][:self.max_items]
			
			self.need_save = True
			
	# #################################################################################################
	
	def remove(self, wtype, url ):
		if wtype in self.items:
			type_root = self.items[wtype]
			i = 0
			for x in type_root:
				if x['url'] == url:
					del self.items[wtype][i]
					self.need_save = True
					break
				i += 1

	# #################################################################################################
	
	def set_last_position(self, url, position ):
		if self.max_items > 0:
			if not 'last_played_position' in self.items:
				self.items['last_played_position'] = {}
			
			lp = self.items['last_played_position']
			
			lp[url] = { 'pos': position, 'time': int(time.time()) }
			self.need_save = True
			self.clean()

	# #################################################################################################
	
	def get_last_position(self, url ):
		if 'last_played_position' in self.items:
			return self.items['last_played_position'].get(url, {}).get('pos', 0)
		
		return 0
		
# #################################################################################################

cache = ExpiringLRUCache( 100, 3600 )

class StreamCinemaContentProvider(ContentProvider):
	kraska = None
	kraska_init_params = None
	webshare = None
	webshare_init_params = None
	watched = None
	watched_init_params = None
	
	# #################################################################################################
	
	def __init__(self, device_id=None, data_dir=None, session=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'stream-cinema', tmp_dir=tmp_dir)
		self.device_id = device_id
		self.data_dir = data_dir
		self.session = session
		
		lang = addon.getSetting('lang')
		
		if lang == 'SK':
			self.lang_code='sl'
			self.lang_list = ['sk', 'cs', 'en']
		elif lang == 'CZ':
			self.lang_code='cs'
			self.lang_list = ['cs', 'sk', 'en']
		else:
			self.lang_code='en'
			self.lang_list = ['en', 'cs', 'sk']
		
		
		self.settings = {
			"show-genre": addon.getSetting('show-genre') == 'true',
			"old-menu": addon.getSetting('old-menu') == 'true',
			"item-lang-filter": addon.getSetting('item-lang-filter'),
			"stream-lang-filter": addon.getSetting('stream-lang-filter'),
			"max-file-size": int(addon.getSetting('max-file-size')) * (2 ** 30),
			"enable-hevc": addon.getSetting('enable-hevc') == 'true',
			"show-hdr": addon.getSetting('show-hdr') == 'true',
			"show-dv": addon.getSetting('show-dv') == 'true',
			"maturity-rating": _MATURITY_RATING_MAP.get( addon.getSetting('maturity-rating'), "0" ),
			"min-quality": addon.getSetting('min-quality'),
			"max-quality": addon.getSetting('max-quality'),
			"save-last-play-pos": addon.getSetting('save-last-play-pos') == 'true',
			"keep-last-seen": int(addon.getSetting('keep-last-seen')),
			"webshare-primary": addon.getSetting('webshare-primary') == 'true',
			"wsvipdays": int(addon.getSetting('wsvipdays')),
		}

		kruser = addon.getSetting('kruser')
		krpass = addon.getSetting('krpass')
		
		if StreamCinemaContentProvider.kraska and StreamCinemaContentProvider.kraska_init_params == (kruser, krpass):
			self.info("Kraska already loaded")
		else:
			StreamCinemaContentProvider.kraska = Kraska( kruser, krpass, self.data_dir, self.info )
			StreamCinemaContentProvider.kraska_init_params = (kruser, krpass)
			self.info("New instance of Kraska initialised")
			try:
				days_left = StreamCinemaContentProvider.kraska.refresh_login_data()
			except:
				days_left = 0
			
			# update remaining vip days
			if addon.getSetting('krvipdays') != str(days_left):
				addon.setSetting('krvipdays', str(days_left))
			
		self.kraska = StreamCinemaContentProvider.kraska

		wsuser = addon.getSetting('wsuser')
		wspass = addon.getSetting('wspass')

		if StreamCinemaContentProvider.webshare and StreamCinemaContentProvider.webshare_init_params == (wsuser, wspass):
			self.info("WebShare already loaded")
		else:
			StreamCinemaContentProvider.webshare = Webshare( wsuser, wspass, device_id, data_dir=self.data_dir, log_function=self.info )
			StreamCinemaContentProvider.webshare_init_params = (wsuser, wspass)

			try:
				days_left = StreamCinemaContentProvider.webshare.refresh_login_data()
			except:
				days_left = -2
			
			# update remaining vip days
			if addon.getSetting('wsvipdays') != str(days_left):
				addon.setSetting('wsvipdays', str(days_left))
			
			self.info("New instance of Webshare initialised")
		
		self.webshare = StreamCinemaContentProvider.webshare
		
		if StreamCinemaContentProvider.watched and StreamCinemaContentProvider.watched_init_params == self.settings['keep-last-seen']:
			self.info("Watched cache already loaded")
		else:
			StreamCinemaContentProvider.watched = SCWatched( self.data_dir, self.settings['keep-last-seen'] )
			StreamCinemaContentProvider.watched_init_params = self.settings['keep-last-seen']
			self.info("New instance of Watched cache initialised")
		
		self.watched = StreamCinemaContentProvider.watched

	# #################################################################################################
	
	def call_sc_api(self, url, data = None, params = None):
		err_msg = None
		
		if not url.startswith("https://"):
			url = "https://stream-cinema.online/kodi" + url
		
		default_params = {
			'ver': API_VERSION,
			'uid': self.device_id,
			'lang': self.lang_list[0],
		}

		u = urlparse( url )
		default_params.update( dict(parse_qsl( u.query )) )
		url = urlunparse( (u.scheme, u.netloc, u.path, '', '', '') )

		if params:
			default_params.update(params)
		
		if self.settings['item-lang-filter'] == '1':
			default_params.update({'dub': 1, "tit": 1}) # zobraz len filmy s dabingom alebo titulkami
		elif self.settings['item-lang-filter'] == '2':
			default_params.update({'dub': 1}) # zobraz len dabovane filmy

		if self.settings['maturity-rating'] >= 0 :
			default_params.update({"m": self.settings['maturity-rating']}) # rating pre rodicovsku kontrolu

		default_params.update({'gen': 1 if self.settings['show-genre'] else 0 }) # zobraz zaner v nazve polozky
		
		if not params or 'HDR' not in params:
			default_params.update({'HDR': 1 if self.settings['show-hdr'] else 0 }) #zobrazit HDR ano/nie 1/0
		
		if not params or 'DV' not in params:
			default_params.update({'DV': 1 if self.settings['show-dv'] else 0 }) # zobrazit 3D filmy ano/nie 1/0
		
		if self.settings['old-menu']:
			default_params.update({'old': 1 }) # zobrazit povodny typ menu

		try:
			headers = {
				'User-Agent' : 'Kodi/19 (X11; U; Unknown i686) (cs; ver0)',
				'X-Uuid': self.device_id,
			}

			if data:
				resp = requests.post( url, data=data, params=default_params, headers=headers )
			else:
				rurl = url + '?' + urlencode( sorted(default_params.items(), key=lambda val: val[0]) )
				resp = cache.get(rurl)
				if resp:
					self.info("Request found in cache")
				else:
					resp = requests.get( url, params=default_params, headers=headers )
					ttl = 3600
					if 'system' in resp and 'TTL' in resp['system']:
						ttl = int(ret['system']['TTL'])

					cache.put( rurl, resp, ttl )
			
#			with open( "/tmp/sc_last_query.txt", "w" ) as f:
#				f.write( url + '?' + urlencode(default_params) + '\n' )
				
#			with open( "/tmp/sc_last_response.json", "w" ) as f:
#				f.write( resp.text )
			
			if resp.status_code == 200:
				try:
					return resp.json()
				except:
					return {}
			else:
				err_msg = "Neočekávaný návratový kód ze serveru: %d" % resp.status_code
		except Exception as e:
			err_msg = str(e)
		
		if err_msg:
			self.error( "SC_API error for URL %s: %s" % (url, traceback.format_exc()))
			raise Exception( "SC_API: %s" % err_msg )

	
	# #################################################################################################
	
	def capabilities(self):
		return ['categories', 'resolve', 'download', 'stats-ext']

	# #################################################################################################

	def categories(self):
		return self.list('/')

	# #################################################################################################

	def list(self, url, params=None):
		result = []
		
		if url.startswith('#'):
			return self.list_special(url)
			
		resp = self.call_sc_api( url, params=params )
		
		for menu_item in resp.get('menu', {}):
			if menu_item['type'] == 'dir':
				item = self.get_dir_item( menu_item )
			elif menu_item['type'] == 'next':
				item = self.get_dir_item( menu_item )
				item['type'] = 'next'
			elif menu_item['type'] == 'video':
				item = self.get_video_item( menu_item )
			elif menu_item['type'] == 'action':
				if menu_item['action'] == 'csearch':
					item = self.get_search_item( menu_item )
				elif menu_item['action'] == 'last':
					item = self.get_last_seen_dir( menu_item )
				else:
					self.info("UNHANDLED ACTION: %s" % menu_item['action'])
					item = None
			else:
				self.info("UNHANDLED ITEM TYPE: %s" % menu_item['type'])
				item = None
				
			if item:
				if '/latest' not in url:
					menu = self.create_ctx_menu(url, resp.get('filter'), resp.get('system',{}).get('addSortMethods'))
					if 'menu' in item and menu:
						item['menu'].update(menu)
					else:
						item['menu'] = menu
				
				result.append( { k: v for k, v in item.items() if v is not None } )
				
		return result
	
	# #################################################################################################
	
	def list_special(self, url, add_ws_edit=True ):
		result = []

		if url.startswith('#remove-last-seen#'):
			lid, url = url[18:].split('#')
			self.watched.remove(lid, url)
			self.watched.save()
			client.refresh_screen()
			
		elif url.startswith('#last-seen#'):
			lid = url[11:]

			for w in self.watched.get(lid):
				if w['type'] == 'dir':
					item = self.dir_item()
				elif w['type'] == 'video':
					item = self.video_item()

				item.update(w)
				item['menu'] = { 'Odstrániť z videných': { "list": '#remove-last-seen#' + lid + '#' + item['url'] }}
				result.append(item)
		elif url.startswith('#set-sort#'):
			url, sort_methods = url[10:].split('|')
			sort_methods = sort_methods.split('#')
			
			sm_url = []
			titles = []
			for m in sort_methods:
				m = int(m)
				if m in _KODI_SORT_METHODS:
					sm = _KODI_SORT_METHODS[m]
					mn = sm[0]
					if m == 26:
						mn += '_%s' % self.lang_code
						
					sm_url.append(self.update_url_filter(url, 'of', mn))
					titles.append( sm[1] )
				else:
					self.info("UNHANDLED SORT METHOD: %d" % m)
			
			sm_url.append( self.update_url_filter(url, 'of', 'random') )
			titles.append( "Náhodne" )
			
			idx = client.getListInput(self.session, titles, 'Triediť podľa')
			if idx == -1:
				result = self.list(url)
			else:
				result = self.list( sm_url[idx] )

		elif url.startswith('#filter-year#'):
			url = url[13:]
			idx = client.getListInput(self.session, ["Staršie ako", "Mladšie ako", "Presne v danom roku"], 'Vybrať podľa roku')
			if idx != -1:
				cur_year = date.today().year
				idx2 = client.getListInput(self.session, [str(x) for x in range(cur_year, 1949, -1) ], 'Vybrať podľa roku')
				if idx2 != -1:
					year = str(cur_year - idx2)
					url = self.update_url_filter(url, 'y', [ '<', '>', ''][idx] + year)
			
			result = self.list(url)
			
		elif url.startswith('#search-webshare#'):
			wsquery = url[17:]
			if add_ws_edit:
				item = self.dir_item( "Upraviť hľadanie", '#edit-webshare#' + wsquery )
				result.append(item)
			
			for witem in self.webshare.search(wsquery):
				item = self.video_item( '#webshare#' + witem['url'], img=witem['img'])
				item['title'] = "[" + witem['size'] + "] " + witem['title']
				result.append(item)

		elif url.startswith('#edit-webshare#'):
			wsquery = url[15:]
			wsquery = client.getTextInput(self.session, "", wsquery )
			if wsquery is not "":
				result = self.list_special( '#search-webshare#' + wsquery, add_ws_edit=False )
			
		return result
	
	# #################################################################################################
	
	def csearch(self, what, action_id ):
		query = {
			'search': what,
			'id': action_id
		}
		if action_id.startswith('search-people'):
			query.update({'ms': '1'})

		return self.list('/Search/' + action_id, query)
	
	# #################################################################################################
	
	def get_i18n_list(self, i18n_base ):
		for l in self.lang_list:
			if l in i18n_base:
				return i18n_base[l]
			
		return None
		
	# #################################################################################################
	
	def get_dir_item(self, sc_item ):
		url = sc_item.get('url')
		
		visible = sc_item.get('visible', '')
		if visible.startswith('sc://config(stream.dubed') and self.settings['item-lang-filter'] == '2':
			# do not show this item, if only dubed movies are allowed
			return None

		if not url:
			return None
		
#		if url == '/huste': #hack to not show Huste TV dir
#			return None
			
		item = self.dir_item( '', url)
		
		item['title'] = sc_item.get('title')
		info = self.get_i18n_list( sc_item.get('i18n_info', {}) )
		if info:
			item['title'] = info.get('title')
			item['plot'] = info.get('plot')

		if not item['title']: # hack to skip recursive items in Documentary section
			return None
				
		img = sc_item.get('art', {}).get('icon')

		info = self.get_i18n_list( sc_item.get('i18n_art', {}) )
		if info:
			img = info.get('poster')

		if img:
			if img.startswith('http://') or img.startswith('https://'):
				item['img'] = img
			else:
				if img in _KODI_IMG_MAP:
					item['img'] = _KODI_IMG_URL + _KODI_IMG_MAP[ img ]

		return item

	# #################################################################################################
	
	def get_video_item(self, sc_item ):
		item = self.video_item( sc_item['url'] )
		
		info = self.get_i18n_list( sc_item.get('i18n_info') )
		genre = ' / '.join( info.get('genre', []))
		if len(genre) > 0:
			genre = '[' + genre + ']\n'
		
		item['title'] = info.get('title', "???").replace('[LIGHT]','').replace('[/LIGHT]','')
		item['plot'] = genre + info.get('plot')
		item['genre'] = ', '.join( info.get('genre', []))
		sorttitle = info.get('sorttitle','')
		
		info = self.get_i18n_list( sc_item.get('i18n_art') )		
		item['img'] = info.get('poster')
		
		info = sc_item.get('info',{})
		item['year'] = info.get('year')
		item['duration'] = int(info.get('duration', 0))
		item['rating'] = info.get('rating')

		if 'episode' in info and 'season' in info and 'tvshowtitle' in info:
			wsquery = info['tvshowtitle'].split(' - [B]')[0].replace(' ','-')+'-S' + str(info['season']).zfill(2)+'E'+str(info['episode']).zfill(2)+'-' + str(info.get('year',''))
		else:
			wsquery = sorttitle.split('-b-')[0] + '-' + str(info.get('year',""))
		
		if self.settings['webshare-primary']:
			item['url'] = "#search-webshare#" + wsquery
			item['type'] = 'dir'
		elif self.settings['wsvipdays'] > 0:
			item['menu'] = { "Vyhľadať na webshare": { "list": "#search-webshare#" + wsquery }}
		
		return item
	
	# #################################################################################################
	
	def get_search_item(self, sc_item ):
		item = self.dir_item( sc_item.get('title'), sc_item.get('id'), 'csearch')
		
		info = self.get_i18n_list( sc_item.get('i18n_info') )
		item['title'] = info.get('title')
		
		item['img'] = sc_item.get('art', {}).get('icon')
		return item

	# #################################################################################################

	def get_last_seen_dir(self, sc_item ):
		lid = sc_item.get('id')
		
		# if there are no items in history, then do not show this dir
		if len(self.watched.get(lid)) == 0:
			return None
		
		item = self.dir_item( sc_item.get('title'), '#last-seen#' + lid )
		
		info = self.get_i18n_list( sc_item.get('i18n_info') )
		item['title'] = info.get('title')
		
		item['img'] = sc_item.get('art', {}).get('icon')
		return item
		
	# #################################################################################################
	
	def update_url_filter(self, url, key, value ):
		u = urlparse( url )
		q = dict(parse_qsl( u.query ))
		if value:
			q.update( { key: value } )
		elif value in q:
			del q[value]
		
		res = urlunparse( ('', '', u.path, '', urlencode(q), '') )
		return res
		
	# #################################################################################################
	
	def create_ctx_menu(self, url, filter, sort_methods ):
		if not filter:
			# nothing to filter
			return None
		
		result = {}
		
		od = filter.get('od', '')
		if od == 'asc':
			url2 = self.update_url_filter( url, 'od', 'desc')
			result["Zoradiť zostupne (Z-A)"] = { "list": url2 }
		elif od == "desc":
			url2 = self.update_url_filter( url, 'od', 'asc')
			result["Zoradiť vzostupne (A-Z)"] = { "list": url2 }
		
		if sort_methods and 0 not in sort_methods:
			result["Triediť"] = { "list": '#set-sort#' + url + '|' + '#'.join( [ str(x) for x in sort_methods ] ) }
		
		if od != '':
			result["Filtrovať podľa roku"] = { "list": '#filter-year#' + url }
		
		return result
	
	# #################################################################################################
	
	def create_video_item(self, stream, info_item ):
		file_url = None
		
		if stream['provider'] == 'kraska':
			try:
				ident = self.call_sc_api(stream['url']).get('ident')
				file_url = self.kraska.resolve( ident )
			except Exception as e:
				client.add_operation('SHOW_MSG', { 'msg': str(e), 'msgType': 'error', 'msgTimeout': 0, 'canClose': True, })
		else:
			client.add_operation('SHOW_MSG', { 'msg': "Nepodporovaný prvider: %s" % stream['provider'], 'msgType': 'error', 'msgTimeout': 0, 'canClose': True, })

		if not file_url:
			return None
		
		subs_url = stream.get('subs')
		
		if subs_url and subs_url.startswith('https://kra.sk/file/'):
			subs_url = subs_url[20:]

			try:
				subs_url = self.kraska.resolve( subs_url )
				self.info("RESOLVED SUBS: %s" % subs_url )
			except:
				# ignore problems with subtitles
				subs_url = None
				pass
		
		item = self.video_item( file_url )
		item['title'] = stream['title']
		item['quality'] = stream['quality']
		item['customDataItem'] = info_item
		
		last_position = self.watched.get_last_position( info_item.get('url') )
		duration = info_item.get('duration')
		if last_position > 0 and (not duration or last_position < duration):
			if client.getYesNoInput(self.session, "Obnoviť prehrávanie od poslednej pozície?"):
				item['playerSettings'] = { 'resume_time_sec' : last_position }
		
		if subs_url:
			item['subs'] = subs_url
			
		return item
	
	# #################################################################################################

	def parse_hr_size( self, size ):
		units = {"B": 1, "KB": 2**10, "MB": 2**20, "GB": 2**30, "TB": 2**40}
		
		number, unit = [string.strip() for string in size.split()]
		return int(float(number)*units[unit])
	
   # #################################################################################################
   
	def filter_streams(self, streams ):
		result = []
		
		for strm in streams:
			self.info( "Filtering stream")
			
			# stream size filter
			if self.settings['max-file-size'] > 0:
				if self.parse_hr_size(strm.get('size', '0 B')) > self.settings['max-file-size']:
					self.debug( "Stream filtered due size")
					continue
			
			# hevc filter
			if not self.settings['enable-hevc'] and strm.get('stream_info',{}).get('HEVC',0) == 1:
				self.debug( "Stream filtered due HEVC")
				continue
			
			strm_quality = strm.get('quality')
			if strm_quality:
				try:
					strm_quality = int(strm_quality.replace('p','').replace('i','').replace('k', '000').replace('K', '000'))
				except:
					# SD quality
					strm_quality = 640

				# min quality filter: Všetko|720p|1080p|4k
				try:
					min_quality = int(self.settings['min-quality'].replace('p','').replace('k', '000'))
				except:
					# All available
					min_quality = 0
				
				if strm_quality < min_quality:
					self.debug( "Stream filtered due min quality")
					continue
				
			
				# max quality filter: 720p|1080p|4k|8k
				try:
					max_quality = int(self.settings['max-quality'].replace('p','').replace('k', '000'))
				except:
					# This should not happen :-(
					max_quality = 8000
				
				if strm_quality > max_quality:
					self.debug( "Stream filtered due max quality")
					continue

			
			#lang filter
			# ALL|CZ or SK|CZ|SK|EN
			item_lang_filter = self.settings['item-lang-filter']
			lang_filter = self.settings['stream-lang-filter']
			avail_langs = strm.get('stream_info',{}).get('langs')
			
			if lang_filter != '0' and avail_langs:
					if lang_filter == '1': # CZ or SK
						ll = [ 'CZ', 'SK']
					elif lang_filter == '2': # CZ
						ll = [ 'CZ' ]
					elif lang_filter == '3': # SK
						ll = [ 'SK' ]
					elif lang_filter == '2': # EN
						ll = [ 'EN', 'EN+tit']
					else:
						ll = []

					for l in ll:
						if l in avail_langs:
							break
					else:
						# configured lang not found in available languages
						
						# if show all items or show dubed or with subtitles is set, then check also if there are subtitles available
						if item_lang_filter == '0' or item_lang_filter == '1':
							# check if there are subtitles available
							for a in avail_langs:
								if '+tit' in a:
									break
							else:
								self.debug( "Stream filtered due lang 1")
								continue
						else:
							self.debug( "Stream filtered due lang 2")
							continue
			
			self.info( "Stream added")
			# strm passed filtering
			result.append(strm)
			
		return result
	
	# #################################################################################################

	def resolve_video_streams(self, url ):
		# get info about files from stream cinema
		result = self.call_sc_api(url)
		
		streams = result.get('strms')
		if not streams:
			return None
		
		streams_filtered = self.filter_streams( streams )
		
		if len( streams_filtered ) > 0:
			streams = streams_filtered
			if len(streams) == 1:
				return self.create_video_item( streams[0], result.get('info') )
		else:
			# no stream passed filtering - let the user decide what now
			pass
		
		titles = []
		for strm in streams:
			title = "[%s%s][%s][%s][%s]" % (strm['quality'], strm['vinfo'], strm['size'], strm['lang'], strm['ainfo'][2:].replace('[','').replace(']',''))
			titles.append( title )
			
		idx = client.getListInput(self.session, titles, '')
		if idx == -1:
			return None
		
		return self.create_video_item(streams[idx], result.get('info'))
	
	# #################################################################################################

	def resolve(self, item, captcha_cb=None, select_cb=None):
		url = item['url']
		
		if url == '#':
			return None
		elif url.startswith( '#webshare#' ):
			return self.video_item( self.webshare.resolve( url[10:] ) )
		
		return self.resolve_video_streams( url )
	
	# #################################################################################################
	
	def stats_ext(self, item, action, extra_params):
		if item:
			url = item.get('url')
			lid = item.get('lid')
		else:
			url = None
			lid = None
		
		try:
			if action.lower() == 'play':
				if url and lid:
					if url.count('/') > 2: # episode or serie -> convert to root item
						title = self.get_i18n_list( item.get('i18n_info', {}) ).get('otitle')
						
						if not title:
							title = item.get('info',{}).get('tvshowtitle') or item.get('info',{}).get('originaltitle')
	
						save_item = {
							"type": "dir",
							'title': title,
							'url': '/FGet/' + item['id'],
							'img': self.get_i18n_list( item.get('i18n_art', {}) ).get('poster')
						}
					else:
						item['type'] = 'video'
						save_item_tmp = self.get_video_item(item)
						save_item = {
							"type": "video",
							'url': save_item_tmp['url'],
							'title': save_item_tmp['title'],
							'plot': save_item_tmp.get('plot'),
							'rating': save_item_tmp.get('rating'),
							'img': save_item_tmp.get('img'),
							'genre': save_item_tmp.get('genre'),
							'year': save_item_tmp.get('year'),
							'duration': save_item_tmp.get('duration'),
						}
						
					self.watched.set( lid, { k: v for k, v in save_item.items() if v is not None } )
				
			elif action.lower() == 'watching':
				pass
				
			elif action.lower() == 'end':
				last_play_pos = extra_params.get('lastPlayPos')
				if url and last_play_pos and self.settings['save-last-play-pos']:
					self.watched.set_last_position( url, last_play_pos )
					
				self.watched.save()
				
		except:
			self.error("Stats processing failed")
			util.error(traceback.format_exc())

	# #################################################################################################