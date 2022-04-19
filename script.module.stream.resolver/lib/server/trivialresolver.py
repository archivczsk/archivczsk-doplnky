# *	 GNU General Public License for more details.
# *
# *	 You should have received a copy of the GNU General Public License
# *	 along with this program; see the file COPYING.	 If not, write to
# *	 the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *	 http://www.gnu.org/copyleft/gpl.html
# *
# */
import re
__name__='simple'
__priority__ = -2
def supports(url):
	return not _regex(url) == None

# returns the steam url
def resolve(url):
	if supports(url):
		return [{'url':url}]

def _regex(url):
	return re.search('\.(flv|mp4|avi|wmv)$',url,re.IGNORECASE | re.DOTALL)

