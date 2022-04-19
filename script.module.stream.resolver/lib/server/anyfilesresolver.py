# -*- coding: UTF-8 -*-
# *	 GNU General Public License for more details.
# *
# *
# *	 You should have received a copy of the GNU General Public License
# *	 along with this program; see the file COPYING.	 If not, write to
# *	 the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *	 http://www.gnu.org/copyleft/gpl.html
# *
# *
# *	 thanks to http://code.google.com/p/sd-xbmc/
# */

import re
import random
import decimal

import util

try:
	from urllib2 import urlopen
except:
	from urllib.request import urlopen

__name__='anyfiles'

BASE_URL = 'http://video.anyfiles.pl'

def supports(url):
	return not _regex(url) == None

def _gen_random_decimal(i, d):
		return decimal.Decimal('%d.%d' % (random.randint(0, i), random.randint(0, d)))


def _decode(param):
	#-- define variables
	loc_3 = [0,0,0,0]
	loc_4 = [0,0,0]
	loc_2 = ''
	#-- define hash parameters for decoding
	dec = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='
	hash1 = ["L", "y", "c", "X", "2", "M", "a", "l", "p", "5", "Q", "e", "R", "t", "Z", "Y", "9", "m", "d", "0", "s", "V", "b", "3", "7", "="]
	hash2 = ["i", "B", "v", "U", "H", "4", "D", "n", "k", "8", "x", "T", "u", "G", "w", "f", "N", "J", "6", "W", "1", "g", "z", "o", "I", "r"]
	hash1 = ["c", "u", "4", "V", "z", "5", "k", "m", "y", "p", "L", "J", "I", "d", "0", "M", "9", "e", "3", "8", "v", "l", "i", "7", "n", "="];
	hash2 = ["t", "Y", "T", "x", "B", "g", "G", "b", "2", "X", "1", "R", "a", "N", "w", "Q", "f", "W", "U", "D", "Z", "s", "6", "H", "o", "r"]

	#-- decode
	for i in range(0, len(hash1)):
		re1 = hash1[i]
		re2 = hash2[i]

		param = param.replace(re1, '___')
		param = param.replace(re2, re1)
		param = param.replace('___', re2)

	i = 0
	while i < len(param):
		j = 0
		while j < 4 and i+j < len(param):
			loc_3[j] = dec.find(param[i+j])
			j = j + 1

		loc_4[0] = (loc_3[0] << 2) + ((loc_3[1] & 48) >> 4);
		loc_4[1] = ((loc_3[1] & 15) << 4) + ((loc_3[2] & 60) >> 2);
		loc_4[2] = ((loc_3[2] & 3) << 6) + loc_3[3];

		j = 0
		while j < 3:
			if loc_3[j + 1] == 64:
				break
			try:
				loc_2 += unichr(loc_4[j])
			except:
				pass
			j = j + 1

		i = i + 4;

	return loc_2

def resolve(url):
	m = _regex(url)
	if m:
		resp = urlopen(url)
		sessc = resp.headers.get('Set-Cookie').split(';')[0]
		resp.close()
		furl = "%s/w.jsp?id=%s&width=620&height=349&pos=&skin=0" % (BASE_URL,m.group('id'))
		headers = {'Cookie':sessc, 'Referer':url}
		data = util.request(furl,headers)
		m1 = re.search('document.cookie = "([^"]+?)"',data)
		m2 = re.search('src="(\/pcsevlet\?code=[^"]+)', data)
		if m1 and m2:
			headers['Cookie'] = headers['Cookie'] + '; ' + m1.group(1)
			headers['Referer'] = BASE_URL + '/flowplayer/flowplayer.commercial-3.2.16.swf'
			data = util.request(BASE_URL + m2.group(1),headers)
			m_vurl = re.search("'url':.*?'(http[^']+?mp4)'", data, re.DOTALL)
			m_surl = re.search("'captionUrl':.*?'(http[^']+)'",data, re.DOTALL)
			if m_vurl:
				resolved = {'url':m_vurl.group(1).strip(),'quality':'???'}
				if m_surl:
					resolved['subs'] = m_surl.group(1).strip()
				return [resolved]
			else:
				return []
def _regex(url):
	return re.search('video\.anyfiles\.pl/w\.jsp\?id=(?P<id>\d+)',url,re.IGNORECASE | re.DOTALL)
