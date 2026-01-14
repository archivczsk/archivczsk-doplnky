import os
from tools_archivczsk.contentprovider.archivczsk_provider import ArchivCZSKContentProvider

from .http_handler import iVysilaniHTTPRequestHandler
from .provider import iVysilaniContentProvider

# #################################################################################################

def main(addon):
	return ArchivCZSKContentProvider(iVysilaniContentProvider, addon, http_cls=iVysilaniHTTPRequestHandler, resources_dir=os.path.join(addon.get_info('path'), 'resources'))
