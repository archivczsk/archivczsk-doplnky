# -*- coding: UTF-8 -*-
# /*
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
import os
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.contentprovider.provider import ResolveException
from tools_xbmc.resolver import resolver
from tools_xbmc.tools import xbmcutil
from tools_xbmc.compat import XBMCCompatInterface
from .videacesky import VideaceskyContentProvider

__scriptid__ = 'plugin.video.videacesky.cz'
__scriptname__ = 'videacesky.cz'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)

__language__ = __addon__.getLocalizedString
__settings__ = __addon__.getSetting

settings = {'quality':__addon__.getSetting('quality')}


def vp8_youtube_filter(stream):
	# some embedded devices running xbmc doesnt have vp8 support, so we
	# provide filtering ability for youtube videos
	
	#======================================================================
	#	  5: "240p h263 flv container",
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
		if stream['fmt'] in [38, 44, 45, 46, 100, 101, 102]:
			return True
	except KeyError:
		return False
	return False


class VideaceskyXBMCContentProvider(XBMCMultiResolverContentProvider):
	
	def play(self, params):
		stream = self.resolve(params['play'])
		print( type(stream) )
		if isinstance(stream, type([])):
			sdict={}
			for s in stream:
				if s['surl'] not in sdict:
					sdict[s['surl']] = s
				if len(sdict) > 1:
					break
			else:
				return XBMCMultiResolverContentProvider.play(self, params)
				
			# resolved to mutliple files, we'll feed playlist and play the first one
			playlist = []
			i = 0
			for video in stream:
				i += 1
				if 'headers' in list(video.keys()):
					playlist.append(xbmcutil.create_play_it(params['title'] + " [" + str(i) + "]", "", video['quality'], video['url'], subs=video['subs'], filename=params['title'], headers=video['headers']))
				else:
					playlist.append(xbmcutil.create_play_it(params['title'] + " [" + str(i) + "]", "", video['quality'], video['url'], subs=video['subs'], filename=params['title']))
			xbmcutil.add_playlist(params['title'], playlist)
		elif stream:
			if 'headers' in list(stream.keys()):
				xbmcutil.add_play(params['title'], "", stream['quality'], stream['url'], subs=stream['subs'], filename=params['title'], headers=stream['headers'])
			else:
				xbmcutil.add_play(params['title'], "", stream['quality'], stream['url'], subs=stream['subs'], filename=params['title'])

	def resolve(self, url):
		def select_cb(resolved):
			stream_parts = []
			stream_parts_dict = {}
			
			for stream in resolved:
				if stream['surl'] not in stream_parts_dict:
					stream_parts_dict[stream['surl']] = []
					stream_parts.append(stream['surl'])
				if __settings__('filter_vp8') and vp8_youtube_filter(stream):
					continue
				stream_parts_dict[stream['surl']].append(stream)

			if len(stream_parts) == 1:
				quality = self.settings['quality'] or '0'
				resolved = resolver.filter_by_quality(stream_parts_dict[stream_parts[0]], quality)
				# if user requested something but 'ask me' or filtered result is exactly 1
				if len(resolved) == 1 or int(quality) > 0:
					return resolved[0]
				return resolved
			# requested to play all streams in given order - so return them all
			return [stream_parts_dict[p][0] for p in stream_parts]

		item = self.provider.video_item()
		item.update({'url':url})
		try:
			return self.provider.resolve(item, select_cb=select_cb)
		except ResolveException as e:
			self._handle_exc(e)


def videacesky_run(session, params):
	VideaceskyXBMCContentProvider(VideaceskyContentProvider(), settings, __addon__, session).run(params)

def main(addon):
	return XBMCCompatInterface(videacesky_run)
