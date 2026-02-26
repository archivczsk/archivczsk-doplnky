# -*- coding: utf-8 -*-
import os
import ctypes
from binascii import unhexlify
from .pssh import cenc_init

API_LEVEL = 1

mp4modify_lib = None
libc = ctypes.CDLL(ctypes.util.find_library('c'))
libc.free.argtypes = (ctypes.c_void_p,)
libc.free.restype = None

def get_mp4modify():
	global mp4modify_lib

	if mp4modify_lib == None:
		from Plugins.Extensions.archivCZSK.engine.tools.stbinfo import stbinfo
		mp4modify_lib = ctypes.CDLL( os.path.join(os.path.dirname(__file__), 'lib', 'mp4modify_%s_%d.so' % (stbinfo.hw_arch, API_LEVEL)) )
		mp4modify_lib.mp4_cenc_info_remove.argtypes = (ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_int))
		mp4modify_lib.mp4_decrypt.argtypes = (ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_int))
		mp4modify_lib.mp4_pssh_get.argtypes = (ctypes.c_char_p, ctypes.c_int)
		mp4modify_lib.mp4_pssh_get.restype = ctypes.POINTER(ctypes.c_char)

	return mp4modify_lib


def mp4decrypt(keys, init_data, enc_data):
	keys_clist = (ctypes.c_char_p * (len(keys) + 1))()
	for i, k in enumerate(keys):
		keys_clist[i] = k.encode('ascii')

	keys_clist[ len(keys) ] = None

	out_ptr = ctypes.c_char_p()
	out_size = ctypes.c_int()
	get_mp4modify().mp4_decrypt(init_data, len(init_data), enc_data, len(enc_data), keys_clist, ctypes.byref(out_ptr), ctypes.byref(out_size))
	result = ctypes.string_at(out_ptr, out_size.value)
	libc.free(out_ptr)
	return result

def mp4_cenc_info_remove(data):
	out_ptr = ctypes.c_char_p()
	out_size = ctypes.c_int()
	get_mp4modify().mp4_cenc_info_remove(data, len(data), ctypes.byref(out_ptr), ctypes.byref(out_size))
	result = ctypes.string_at(out_ptr, out_size.value)
	libc.free(out_ptr)
	return result

def mp4_pssh_get(data):
	ret = get_mp4modify().mp4_pssh_get(data, len(data))
	wv_pssh, pr_pssh, kid = ctypes.cast(ret, ctypes.c_char_p).value.split(b';')
	libc.free(ret)

	return cenc_init(unhexlify(wv_pssh)) if wv_pssh else None, cenc_init(unhexlify(pr_pssh)) if pr_pssh else None, kid.decode('ascii')[8:].lower()
