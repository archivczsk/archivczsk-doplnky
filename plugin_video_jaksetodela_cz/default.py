# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2013 Ivo Brhel
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
sys.path.append( os.path.join ( os.path.dirname(__file__),'resources','lib') )

import re,os
import util,xbmcprovider,xbmcutil
import jaksetodela
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

__scriptid__   = 'plugin.video.jaksetodela.cz'
__scriptname__ = 'jaksetodela.cz'
__addon__	   = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__   = __addon__.getLocalizedString

settings = {'quality':__addon__.getSetting('quality')}

xbmcprovider.XBMCMultiResolverContentProvider(jaksetodela.JaksetodelaContentProvider(),settings,__addon__,session).run(params)


