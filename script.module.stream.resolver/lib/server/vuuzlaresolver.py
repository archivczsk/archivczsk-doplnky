# *	 GNU General Public License for more details.
# *
# *	 You should have received a copy of the GNU General Public License
# *	 along with this program; see the file COPYING.	 If not, write to
# *	 the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *	 http://www.gnu.org/copyleft/gpl.html
# *
# */
import re,util

__name__='vuuzla'
def supports(url):
	return not _regex(url) == None

# returns the steam url
def resolve(url):
	m = _regex(url)
	if m:
		data = util.request(url)
		sid = re.search('sid=(?P<sid>[^\&]+)',data)
		if sid:
			data = util.request('http://www.vuuzla.com/app/deliver/playlist/%s?sid=%s' % (m.group('id'),sid.group('sid')))
			link = re.search('<video.+?url=\"(?P<url>[^\"]+)',data)
			if link:
				return [{'url':link.group('url')}]

def _regex(url):
	return re.search('www\.vuuzla\.com.+?playerFrame/(?P<id>[^$]+)',url,re.IGNORECASE | re.DOTALL)

