# -*- coding: utf-8 -*-

from .YouTubeVideoUrl import YouTubeVideoUrl
from .fake_config import config
import re

def resolve(url, settings=None):
	id_object = re.search('((?<=(v|V)/)|(?<=be/)|(?<=(\?|\&)v=)|(?<=embed/))([\w-]+)', url, re.DOTALL)

	if id_object is not None:
		url = id_object.group(0)

	config.set_addon_settings(settings)
	youtube = YouTubeVideoUrl()
	return youtube.extract(url)
