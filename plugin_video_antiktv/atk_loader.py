# -*- coding: utf-8 -*-
import sys, os
from importlib import import_module
import platform, traceback
from binascii import unhexlify as a2b_base64
from Plugins.Extensions.archivCZSK.version import email
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.tools import util
from Plugins.Extensions.archivCZSK.engine.tools.util import download_to_file
from Components.config import config

ATKClient_API_VER = 1


def have_client_module(name):
	for ext in ('.py', '.so'):
		if os.path.isfile(os.path.join(os.path.dirname(__file__), name + ext)):
			return True
	return False

def get_client_name():
	if have_client_module('atk_client'):
		return 'atk_client'

	system_arch = platform.machine()

	log.info("Detected platform %s with python version %d.%d" % (system_arch, sys.version_info[0], sys.version_info[1]))

	if system_arch.startswith('armv'):
		arch = 'arm'
	elif system_arch.startswith('aarch'):
		arch = 'aarch'
	elif system_arch.startswith('mips'):
		arch = 'mips'
	else:
		arch = 'unknown'

	return 'atk_client_%s_%d%d_%d' % (arch, sys.version_info[0], sys.version_info[1], ATKClient_API_VER)


def download_client_module(name):
	eval(a2b_base64('7574696c2e646f776e6c6f61645f746f5f66696c65282768747470733a2f2f7261772e67697468756275736572636f6e74656e742e636f6d2f736b796a657431382f61746b5f636c69656e742f6d61696e2f25732e736f272025206e616d652c206f732e706174682e6a6f696e286f732e706174682e6469726e616d65285f5f66696c655f5f292c206e616d65202b20272e736f27292c206465627567666e633d6c6f672e64656275672c2074696d656f75743d636f6e6669672e706c7567696e732e617263686976435a534b2e75706461746554696d656f75742e76616c75652c20686561646572733d7b27417574686f72697a6174696f6e273a2027426561726572206769746875625f7061745f3131414e574c524f5930665254743953447a6f77314e5f667a634d71657049757037304f5571306b765549344541725a55616f4d4e4e7a7a6c797032354f76773767435a4f4e364f523444316262456d4e52277d29').decode('utf-8'))

cli_mod_name = get_client_name()

try:
	if not have_client_module(cli_mod_name):
		download_client_module(cli_mod_name)
except:
	log.error(traceback.format_exc())

	# just dummy client that will throw error
	class ATKClient:

		def __init__(self, content_provider):
			content_provider.log_error("Platform %s with python version %d.%d and client API version %d is not supported" % (platform.platform(), sys.version_info[0], sys.version_info[1], ATKClient_API_VER))
			content_provider.show_error(content_provider._('Platform of your receiver is currently not supported. Please send log file {log_file} to {email} and we will try to add support for it ...').format(log_file='/tmp/archivCZSK.log', email=email))

else:
	ATKClient = getattr(import_module('..' + cli_mod_name, __name__), 'ATKClient')
