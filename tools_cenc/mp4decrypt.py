# -*- coding: utf-8 -*-
import os
import ctypes

mp4modify_lib = None

def get_mp4modify():
	global mp4modify_lib

	if mp4modify_lib == None:
		from Plugins.Extensions.archivCZSK.engine.tools.stbinfo import stbinfo
		mp4modify_lib = ctypes.CDLL( os.path.join(os.path.dirname(__file__), 'lib', 'mp4modify_%s.so' % stbinfo.hw_arch) )
		mp4modify_lib.mp4_cenc_info_remove.argtypes = (ctypes.c_char_p, ctypes.c_int)
		mp4modify_lib.mp4_decrypt.argtypes = (ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_char_p))

	return mp4modify_lib


def mp4decrypt(keys, init_data, enc_data):
	keys_clist = (ctypes.c_char_p * (len(keys) + 1))()
	for i, k in enumerate(keys):
		keys_clist[i] = k.encode('utf-8')

	keys_clist[ len(keys) ] = None

	# WARNING: this function will modify pythons internal enc_data buffer !!!
	ret = get_mp4modify().mp4_decrypt(init_data, len(init_data), enc_data, len(enc_data), keys_clist)
	x = enc_data[:ret]

	return x

def mp4_cenc_info_remove(data):
	# needed to create copy of data, because function will modify it
	data = data + b'X'
	ret = get_mp4modify().mp4_cenc_info_remove(data, len(data)-1)
	return data[:ret]
