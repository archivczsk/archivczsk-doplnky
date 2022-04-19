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
import util,re
__name__ = 'novamov'
def supports(url):
	return not _regex(url) == None

def resolve(url):
	if supports(url):
		data = util.request(url)
		m = re.search('flashvars.file=\"([^\"]+)',data,re.IGNORECASE | re.DOTALL)
		n = re.search('flashvars.filekey=\"([^\"]+)',data,re.IGNORECASE | re.DOTALL)
		if not m == None and not n == None:
			data = util.request('http://www.novamov.com/api/player.api.php?key=%s&file=%s&user=undefined&pass=undefined&codes=1' % (n.group(1),m.group(1)))
			stream = re.search('url=([^\&]+)',data).group(1)
			return [{'url':stream}]

def _regex(url):
	return re.search('novamov\.com',url,re.IGNORECASE | re.DOTALL)
