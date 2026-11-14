import os
try:
	from typing import Optional
except ImportError:
	pass

from ..system.compat import write_file

class Storage(object):

	@staticmethod
	def _get_initialized_path():
		return "/tmp"

	@staticmethod
	def write_file(file_name, data):
		storage_path = Storage._get_initialized_path()
		storage_file = os.path.join(storage_path, file_name)

		new_file = not os.path.exists(storage_file)

		write_file(storage_file, data)

		return new_file

	@staticmethod
	def read_file(file_name):
		storage_path = Storage._get_initialized_path()
		storage_file = os.path.join(storage_path, file_name)

		if not os.path.exists(storage_file):
			return None

		with open(storage_file, "rb") as stream:
			return stream.read()
