
# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2011 Libor Zoubek
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
import os,re,sys
from . import xbmcutil
from . import util
from Plugins.Extensions.archivCZSK.engine import client

def _list(addon,history,key,value):
	params = {}
	menuItems = {}
	if key:
		params[key] = value
		menuItems[key] = value
	params['search'] = ''
	xbmcutil.add_search_item(xbmcutil.__lang__(30004),params,xbmcutil.icon('search.png'))
	for what in xbmcutil.get_searches(addon,history):
		params = {}
		menuItems={}
		if key:
			params[key] = value
			menuItems[key] = value
		params['search'] = what
		menuItems['search-remove'] = what
		xbmcutil.add_dir(what,params,menuItems={u"Remove":menuItems})

def _remove(addon,history,search):
	xbmcutil.remove_search(addon,history,search)
	client.refresh_screen()

def _search(session,addon,history,what,update_history,callback):
	if what == '':
		what = client.getTextInput(session,xbmcutil.__lang__(30003))
	if not what == '':
		maximum = 20
		try:
			maximum = int(addon.get_setting('keep-searches'))
		except:
			util.error('Unable to parse convert addon setting to number')
			pass
		if update_history:
			xbmcutil.add_search(addon,history,what,maximum)
		callback(what)

def item(items={},label=xbmcutil.__lang__(30003)):
	items['search-list'] = ''
	xbmcutil.add_search_folder(label,items,xbmcutil.icon('search.png'))

def main(session,addon,history,p,callback,key=None,value=None):
	if (key==None) or (key in p and p[key] == value):
		if 'search-list' in list(p.keys()):
			_list(addon,history,key,value)
		if 'search' in list(p.keys()):
			update_history=True
			if 'search-no-history' in list(p.keys()):
				update_history=False
			_search(session,addon,history,p['search'],update_history,callback)
		if 'search-remove' in list(p.keys()):
			_remove(addon,history,p['search-remove'])
