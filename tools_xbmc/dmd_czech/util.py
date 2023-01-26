'''
Created on 25.10.2012

@author: marko
'''
from Plugins.Extensions.archivCZSK.engine.client import add_dir, add_video, getSearch, showError,showInfo,showWarning

def addDir(name, url, mode, image, page=None, kanal=None, infoLabels={}, menuItems={}):
	params = {'name':name, 'url':url, 'mode':mode, 'page':page, 'kanal':kanal}
	add_dir(name, params, image, infoLabels=infoLabels, menuItems=menuItems)
	
def addSearch(name, url, mode, image, page=None, kanal=None, infoLabels={}, menuItems={}):
	params = {'name':name, 'url':url, 'mode':mode, 'page':page, 'kanal':kanal}
	add_dir(name, params, image, infoLabels=infoLabels, menuItems=menuItems,search_item=True)

def addLink(name, url, image, *args, **kwargs):
	add_video(name, url, None, image)

