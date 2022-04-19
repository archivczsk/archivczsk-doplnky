# -*- coding: UTF-8 -*-
# /*
# *		 Copyright (C) 2013 Maros Ondrasek
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
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
import gordonura
import xbmcprovider, xbmcutil
import util, resolver
from provider import ResolveException


__scriptid__ = 'plugin.video.gordon.ura.cz'
__scriptname__ = 'gordon.ura.cz'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString

def vp8_youtube_filter(stream):
	# some embedded devices running xbmc doesnt have vp8 support, so we
	# provide filtering ability for youtube videos
	
	#======================================================================
	#		5: "240p h263 flv container",
	#	   18: "360p h264 mp4 container | 270 for rtmpe?",
	#	   22: "720p h264 mp4 container",
	#	   26: "???",
	#	   33: "???",
	#	   34: "360p h264 flv container",
	#	   35: "480p h264 flv container",
	#	   37: "1080p h264 mp4 container",
	#	   38: "720p vp8 webm container",
	#	   43: "360p h264 flv container",
	#	   44: "480p vp8 webm container",
	#	   45: "720p vp8 webm container",
	#	   46: "520p vp8 webm stereo",
	#	   59: "480 for rtmpe",
	#	   78: "seems to be around 400 for rtmpe",
	#	   82: "360p h264 stereo",
	#	   83: "240p h264 stereo",
	#	   84: "720p h264 stereo",
	#	   85: "520p h264 stereo",
	#	   100: "360p vp8 webm stereo",
	#	   101: "480p vp8 webm stereo",
	#	   102: "720p vp8 webm stereo",
	#	   120: "hd720",
	#	   121: "hd1080"
	#======================================================================
	try:
		if stream['fmt'] in [38, 44, 43, 45, 46, 100, 101, 102]:
			return True
	except KeyError:
		return False
	return False

class GordonUraXBMCContentProvider(xbmcprovider.XBMCMultiResolverContentProvider):
	
	def resolve(self, url):
		def select_cb(resolved):
			if __addon__.getSetting('filter_vp8') == 'true':
				resolved = [r for r in resolved if not vp8_youtube_filter(r)]
			quality = self.settings['quality'] or '0'
			resolved = resolver.filter_by_quality(resolved, quality)
			# if user requested something but 'ask me' or filtered result is exactly 1
			if len(resolved) == 1 or int(quality) > 0:
				return resolved[0]
			return resolved

		item = self.provider.video_item()
		item.update({'url':url})
		try:
			return self.provider.resolve(item, select_cb=select_cb)
		except ResolveException as e:
			self._handle_exc(e)
		
	

settings = {'quality':__addon__.getSetting('quality')}
provider = gordonura.GordonUraContentProvider()

GordonUraXBMCContentProvider(provider, settings, __addon__,session).run(params)