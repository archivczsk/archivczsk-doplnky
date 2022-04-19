from Plugins.Extensions.archivCZSK.engine.client import add_dir, add_video, getSearch, showError,showInfo,showWarning, log

# methods used by standard xbmc plugins
def addDir(name, url, mode, image, page=None, kanal=None, infoLabels={}, menuItems={}):
	params = {'name':name, 'url':url, 'mode':mode, 'page':page, 'kanal':kanal}
	add_dir(name, params, image, infoLabels=infoLabels, menuItems=menuItems)
	
def addLink(name, url, image, *args, **kwargs):
	add_video(name, url, None, image)
	
	
def addSearch(name, url, mode, image, page=None, kanal=None, infoLabels={}, menuItems={}):
	params = {'name':name, 'url':url, 'mode':mode, 'page':page, 'kanal':kanal}
	add_dir(name, params, image, infoLabels=infoLabels, menuItems=menuItems,search_item=True)
