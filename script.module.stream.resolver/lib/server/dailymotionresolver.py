# -*- coding: UTF-8 -*-
# *
# *
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with this program; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# *

import re
from xml.etree import ElementTree
import util
from copy import deepcopy
import json

__name__ = 'dailymotion'


def supports(url):
    return re.search(r'dailymotion.com/embed', url) is not None


def resolve(url):
    print('The url is ::', url)
    id = re.search(r'dailymotion.com/embed/video/(.+)', url).group(1)
    print('The id is ::', id)
    headers = {'User-Agent': 'Android'}
    cookie = {'Cookie': "lang=en; ff=off"}
    r = util.request("http://www.dailymotion.com/player/metadata/video/" + id,
                     headers)
    content = json.loads(r)
    cc = content['qualities']
    cc = list(cc.items())

    cc = sorted(cc, reverse=True)
    m_url = ''
    other_playable_url = []

    items = []
    result = []

    for source, json_source in cc:
        source = source.split("@")[0]
        for item in json_source:

            m_url = item.get('url', None)
            # xbmc.log("DAILYMOTION - m_url = %s" % m_url, xbmc.LOGNOTICE)
            if m_url:
                if source == "auto":
                    continue

                elif '.mnft' in m_url:
                    continue

                if 'video' in item.get('type', None):
                    item = {}
                    item['url'] = m_url
                    item['quality'] = source
                    item['title'] = 'video'
                    items.append(item)

                other_playable_url.append(m_url)

        if items:
            for item in items:
                newitem = deepcopy(item)
                item['lang'] = '???'
                item['headers'] = headers
                result.append(newitem)
    if not result and cc[0][0]=='auto':
        json_source=cc[0][1]
        m_url=json_source[0].get('url', None)
        r = util.request(m_url)
        streams = re.compile(r'RESOLUTION=\d+x(\d+).*\n([^\s]+)').findall(r)   
        for quality, url in streams:
            item = {}
            item['url'] = url
            item['quality'] = quality + 'p'
            item['title'] = 'video'
            result.append(item)
    return result
