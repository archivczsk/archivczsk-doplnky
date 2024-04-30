import routing
import requests
import os
import xbmc
import xbmcvfs
import xbmcaddon
import xbmcgui
import qrcode
import tempfile
import threading
import xbmcplugin
from bs4 import BeautifulSoup
#import inputstreamhelper

addon = xbmcaddon.Addon()
profile = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
plugin = routing.Plugin()

base_url = 'https://kviff.tv/api/'
session = requests.session()
token = addon.getSetting('token')

preferred_size = 'Full HD'

def get_request(url, method='GET'):
	global token
	headers = {'Authorization' : 'Bearer ' + token };
	return session.request(method=method, url=base_url + url, headers=headers)

def get(url, method='GET'):
	ensure_logged_in()

	resp = get_request(url, method)
	if resp.status_code == 401:
		login()
		resp = get_request(url, method)

	if not resp.ok:
		print(resp.content)
		if resp.status_code == 401:
			raise PermissionError()
		resp.raise_for_status()

	return resp.json()

class qr_window(xbmcgui.WindowDialog):
	def __init__(self, code, image_path):
		self.code = code
		size = int(min(xbmcgui.getScreenWidth(), xbmcgui.getScreenHeight()) / 2 - 80)
		self.image = xbmcgui.ControlImage(80, 80, size, size, image_path)
		self.addControl(self.image)
		self.stop_event = threading.Event()
		self.done = False
		self.thread = threading.Thread(target=self.poll)
		self.visible = True
		self.thread.start()
		self.token = ''

	def __del__(self):
		self.thread.join()

	def onAction(self, action):
		if action.getId() == 10:
			self.stop_event.set()
			self.visible = False
			self.close()

	def poll(self):
		while not self.stop_event.is_set():
			check = session.request(method='POST', url=base_url + 'auth/devices/code/login?code=%s'%self.code)
#			xbmc.log(str(check), 3)
			if check.status_code == 200:
				self.token = check.json()['data']['token']
				break
			elif check.status_code != 401:
				break
			self.stop_event.wait(1)
		self.done = True

def ensure_logged_in():
	global token
	if not token:
		info_dlg = xbmcgui.Dialog()
		info_dlg.ok('KVIFF.TV účet', 'Služba KVIFF.TV vyžaduje předplatné. Pokud ho nemáte, tak si ho zařiďte. Na následující stránce se zobrazí QR kód. Naskenujte si ho mobilem a přihlašte se ke svému účtu.')
		auth_data = session.request(method='GET', url=base_url + 'auth/devices/code?language=cs').json()
#		xbmc.log(str(auth_data), 3)
		url = auth_data['data']['qrLink']
		qr = qrcode.QRCode(version=1, box_size=10)
		qr.make(fit=True)
		qr.add_data(qrcode.util.QRData(url))
		img = qr.make_image()
		img_file = tempfile.NamedTemporaryFile(dir=profile,delete=False)
		img.save(img_file)
		qr_win = qr_window(code=auth_data['data']['accessCodeHash'], image_path=img_file.name)

		qr_win.show()
		while not qr_win.done and qr_win.visible:
			xbmc.sleep(100)
		qr_win.close()
		token = qr_win.token
		del qr_win
	if not token:
		xbmcgui.Dialog().ok('KVIFF.TV účet', 'Přihlášení se nezdařilo')
	else:
		addon.setSetting(id='token', value=token)

def extract_text(html):
	soup = BeautifulSoup(html, 'html.parser')
	ps = soup.findAll('p')
	text = ''
	for p in ps:
		text += p.text
		text += '\n'
	if not text:
		text = html
	return text

def make_film_item(f):
	film_list_item = xbmcgui.ListItem(f['title'])
	film_list_item.setProperty('IsPlayable', 'true')
	film_list_item.setArt({'poster': f['image']})
	film_list_item.setInfo('video', {
		'title': f['title'],
		'originaltitle': f['originalTitle'],
		'duration': int(f['duration'] / 1000),
		'plotoutline': extract_text(f['synopsis']),
		'plot': extract_text(f['description']),
		'year': f['year'],
		'director': f['directors'],
		'genre': f['genres'],
		'country': f['countries']
		})

	film_item = (plugin.url_for(play, f['id']), film_list_item, False)
	return film_item


@plugin.route('/login')
def login():
	global token
	token = ''
	ensure_logged_in()
	xbmcplugin.endOfDirectory(plugin.handle)
	xbmc.executebuiltin('Container.Update(%s)'%plugin.url_for(root))

@plugin.route('/logoff')
def logoff():
	global token
	token = ''
	addon.setSetting(id='token', value=token)
	xbmcplugin.endOfDirectory(plugin.handle)
	xbmc.executebuiltin('Container.Update(%s)'%plugin.url_for(root))

@plugin.route('/play/<id>')
def play(id):
	resp = get('player/%s?language=cs'%id)
	playlist = resp['data']['playlist'][0]
	sources = playlist['sources']
#	xbmc.log(str(resp), 3)

	source = ''
	for src in sources:
#		xbmc.log(str(src), 3)
		if src['size'] == preferred_size:
			source = src
			break
	if not source:
		source = sources[0]

	subtitle = ''
	if 'tracks' in playlist:
		for trk in playlist['tracks']:
			if trk['kind'] == 'captions' and trk['default']:
				subtitle = trk['src']
				break;
	item = xbmcgui.ListItem(path=source['url'])
	if subtitle:
		item.setSubtitles([subtitle])

#	xbmc.log(str(item), 3)
	xbmcplugin.setResolvedUrl(plugin.handle, True, item)

@plugin.route('/collection/<id>')
def collection(id):
	resp = get('collection/%s?p=1&pageSize=500&language=cs'%id)
#	xbmc.log(str(resp), 4)
	films = resp['data']['0']['items']
#	xbmc.log(str(films), 4)
	items = []
	for f in films:
#		xbmc.log(str(f), 3)
		items.append(make_film_item(f))
	xbmcplugin.addDirectoryItems(plugin.handle, items, len(items))
	xbmcplugin.endOfDirectory(plugin.handle)
	xbmcplugin.setContent(plugin.handle, "movies")

@plugin.route('/collections')
def collections():
	colls = get('collections?language=cs')
	items = []
	for super_coll in colls['data']:
		if 'items' in super_coll:
			super_coll_items = super_coll['items']
			for coll_key in super_coll_items:
#				xbmc.log(str(super_coll_items), 3)
				coll = super_coll_items[coll_key]

				if 'synopsis' in coll:
					desc = extract_text(coll['synopsis'])
				else:
					desc = ''

				coll_list_item = xbmcgui.ListItem(coll_key)
				coll_list_item.setArt({'poster': coll['image']})
				coll_list_item.setInfo('video', {'plot': desc})

				coll_item = (plugin.url_for(collection, coll['id']), coll_list_item, True)
				items.append(coll_item)
#	xbmc.log(str(items), 3)
	xbmcplugin.addDirectoryItems(plugin.handle, items, len(items))
	xbmcplugin.endOfDirectory(plugin.handle)
	xbmcplugin.setContent(plugin.handle, "movies")

@plugin.route('/genre/<id>')
def genre(id):
	resp = get('genre/%s?p=1&pageSize=500&language=cs'%id)
	films = resp['data'][0]['items']
	items = []
	for f in films:
		items.append(make_film_item(f))
	xbmcplugin.addDirectoryItems(plugin.handle, items, len(items))
	xbmcplugin.endOfDirectory(plugin.handle)
	xbmcplugin.setContent(plugin.handle, "movies")

@plugin.route('/genres')
def genres():
	gnrs = get('home?language=cs')['data']['genres']
	items = []
	for gnr in gnrs:
		gnr_list_item = xbmcgui.ListItem(gnr['title'])
		gnr_item = (plugin.url_for(genre, gnr['id']), gnr_list_item, True)
		items.append(gnr_item)
	xbmcplugin.addDirectoryItems(plugin.handle, items, len(items))
	xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route('/')
def root():
	global token
	try:
		os.mkdir(profile)
	except OSError:
		pass

	try:
		if token:
			colls_item = (plugin.url_for(collections), xbmcgui.ListItem('Kolekce'), True)
			genres_item = (plugin.url_for(genres), xbmcgui.ListItem('Žánry'), True)
			logoff_item = (plugin.url_for(logoff), xbmcgui.ListItem('Odhlásit se'), True)
			xbmcplugin.addDirectoryItems(plugin.handle, [colls_item, genres_item, logoff_item], 3)
		else:
			login_item = (plugin.url_for(login), xbmcgui.ListItem('Přihlásit se'), True)
			xbmcplugin.addDirectoryItems(plugin.handle, [login_item], 1)
		xbmcplugin.endOfDirectory(plugin.handle)
	except PermissionError:
		token = ''
		addon.setSetting(id='token', value=token)
		print('error')

def run():
	plugin.run()
