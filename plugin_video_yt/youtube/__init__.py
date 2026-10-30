# -*- coding: utf-8 -*-

from .YouTubeVideoUrl import YouTubeVideoUrl
from .fake_config import config
import re

def resolve(url, settings=None, with_captions=False):
	'''
	Returns playable url of the video
	with_captions=True returns tuple (url, {'tracks': caption tracks, 'orig_lang': language of original audio track or None})
	'''
	id_object = re.search('((?<=(v|V)/)|(?<=be/)|(?<=(\?|\&)v=)|(?<=embed/))([\w-]+)', url, re.DOTALL)

	if id_object is not None:
		url = id_object.group(0)

	config.set_addon_settings(settings)
	youtube = YouTubeVideoUrl()
	video_url = youtube.extract(url)
	if with_captions:
		return video_url, {'tracks': youtube.caption_tracks, 'orig_lang': youtube.original_lang}
	return video_url
