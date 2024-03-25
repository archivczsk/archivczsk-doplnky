# -*- coding: utf-8 -*-
import os
import subprocess
from Plugins.Extensions.archivCZSK.engine.tools.stbinfo import stbinfo

tmp_file_id = 1
DECRYPT_CMD = os.path.join(os.path.dirname(__file__), 'bin', 'mp4decrypt_%s' % stbinfo.hw_arch)

def mp4decrypt(keys, init_data, enc_data):
	# this is very simple and unefective implementation that blocks reactor and that is definitely not what we want ...
	# needs complete rewrite to async ...
	global tmp_file_id

	# create temp file with segment data
	tmp_file_name_init = os.path.join( '/tmp', '._init_%d.mp4' % tmp_file_id)
	tmp_file_name_in = os.path.join( '/tmp', '._in_%d.m4s' % tmp_file_id)
	tmp_file_name_out = os.path.join( '/tmp', '._out_%d.m4s' % tmp_file_id)
	tmp_file_id += 1
	if tmp_file_id >= 1000:
		tmp_file_id = 1

	with open(tmp_file_name_in, 'wb') as f:
		f.write(enc_data)

	cmd = [DECRYPT_CMD]

	for k in keys:
		cmd.append('--key')
		cmd.append(k)

	if init_data != None:
		with open(tmp_file_name_init, 'wb') as f:
			f.write(init_data)

		cmd.append('--fragments-info')
		cmd.append(tmp_file_name_init)

	cmd.append(tmp_file_name_in)
	cmd.append(tmp_file_name_out)

	try:
		subprocess.check_call( cmd )
	except:
		data_out = None
	else:
		with open(tmp_file_name_out, 'rb') as f:
			data_out = f.read()
	finally:
		if init_data != None:
			os.remove(tmp_file_name_init)

		os.remove(tmp_file_name_in)
		try:
			os.remove(tmp_file_name_out)
		except:
			pass

	return data_out
