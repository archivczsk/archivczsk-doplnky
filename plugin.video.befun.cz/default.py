# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2013 Libor Zoubek
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

sys.path.append(os.path.join (os.path.dirname(__file__), 'resources', 'lib'))
import befun
import xbmcprovider
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
import util
import traceback

__scriptid__ = 'plugin.video.befun.cz'
__scriptname__ = 'befun.cz'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString

order_map = {'0':'', '1':'inverse=0', '2':'order=rating', '3':'order=seen'}
order_by = order_map[__addon__.getSetting('order-by')]

settings = {'quality':__addon__.getSetting('quality'), 'order-by':order_by}

provider = befun.BefunContentProvider()
provider.order_by = order_by
xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)

