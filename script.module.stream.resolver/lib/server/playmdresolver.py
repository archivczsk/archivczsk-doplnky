# *	 GNU General Public License for more details.
# *
# *	 You should have received a copy of the GNU General Public License
# *	 along with this program; see the file COPYING.	 If not, write to
# *	 the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *	 http://www.gnu.org/copyleft/gpl.html
# *
# */
import re,util

__name__='play.md'
def supports(url):
	return not _regex(url) == None


def resolve(link):
	if _regex(link):
		data = util.request(link)
		url = re.search('base_url\: \"(?P<url>[^\"]+)',data)
		file = re.search('file_name\: \"(?P<url>[^\"]+)',data)
		res = re.search('resolutions\: \"(?P<url>[^\"]+)',data)
		if url and file and res:
			url = '%s/%s/%s' % (url.group('url'),res.group('url'),file.group('url'))
			return [{'quality':res.group('url'),'url':url}]

def _regex(url):
	return re.search('play\.md',url,re.IGNORECASE | re.DOTALL)

