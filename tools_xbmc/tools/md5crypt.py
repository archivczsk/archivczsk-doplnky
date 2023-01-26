#########################################################
# md5crypt.py
#
# 0423.2000 by michal wallace http://www.sabren.com/
# based on perl's Crypt::PasswdMD5 by Luis Munoz (lem@cantv.net)
# based on /usr/src/libcrypt/crypt.c from FreeBSD 2.2.5-RELEASE
#
# MANY THANKS TO
#
#  Carey Evans - http://home.clear.net.nz/pages/c.evans/
#  Dennis Marti - http://users.starpower.net/marti1/
#
#  For the patches that got this thing working!
#
#########################################################
"""md5crypt.py - Provides interoperable MD5-based crypt() function

SYNOPSIS

	import md5crypt.py

	cryptedpassword = md5crypt.md5crypt(password, salt);

DESCRIPTION

unix_md5_crypt() provides a crypt()-compatible interface to the
rather new MD5-based crypt() function found in modern operating systems.
It's based on the implementation found on FreeBSD 2.2.[56]-RELEASE and
contains the following license in it:

 "THE BEER-WARE LICENSE" (Revision 42):
 <phk@login.dknet.dk> wrote this file.	As long as you retain this notice you
 can do whatever you want with this stuff. If we meet some day, and you think
 this stuff is worth it, you can buy me a beer in return.	Poul-Henning Kamp

apache_md5_crypt() provides a function compatible with Apache's
.htpasswd files. This was contributed by Bryan Hart <bryan@eai.com>.

"""
from hashlib import md5

ITOA64 = b"./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
MAGIC = b'$1$'

def to64 (v, n):
	ret = b''
	while (n - 1 >= 0):
		n = n - 1
		ret = ret + ITOA64[v & 0x3f:(v & 0x3f)+1]
		v = v >> 6
	return ret

def apache_md5_crypt (pw, salt):
	# change the Magic string to match the one used by Apache
	return unix_md5_crypt(pw, salt, '$apr1$')

def unix_md5_crypt(password, salt, magic=None):
	
	if magic == None:
		magic = MAGIC
	else:
		if not isinstance( magic, bytes):
			magic = magic.encode('ascii')

	if not isinstance( salt, bytes):
		salt = salt.encode('ascii')

	# Take care of the magic string if present
	if salt[:len(magic)] == magic:
		salt = salt[len(magic):]

	if not isinstance( password, bytes):
		password = password.encode('utf-8')

	# /* The password first, since that is what is most unknown */ /* Then our magic string */ /* Then the raw salt */
	m = md5()
	m.update(password + magic + salt)

	# /* Then just as many characters of the MD5(pw,salt,pw) */
	mixin = md5(password + salt + password).digest()

	for i in range(0, len(password)):
		pos = i % 16
		x = mixin[pos:pos + 1]
#		print(type(x))
		m.update(x)

	# /* Then something really weird... */
	# Also really broken, as far as I can tell.	 -m
	i = len(password)
	while i:
		if i & 1:
			m.update(b'\x00')
		else:
			m.update(password[0:1])
		i >>= 1

	final = m.digest()

	# /* and now, just to make sure things don't run too fast */
	for i in range(1000):
		m2 = md5()
		if i & 1:
			m2.update(password)
		else:
			m2.update(final)

		if i % 3:
			m2.update(salt)

		if i % 7:
			m2.update(password)

		if i & 1:
			m2.update(final)
		else:
			m2.update(password)

		final = m2.digest()

	# This is the bit that uses to64() in the original code.

	passwd = b''

	passwd = passwd + to64((int(ord(final[0:1])) << 16)
						   |(int(ord(final[6:7])) << 8)
						   |(int(ord(final[12:13]))),4)

	passwd = passwd + to64((int(ord(final[1:2])) << 16)
						   |(int(ord(final[7:8])) << 8)
						   |(int(ord(final[13:14]))), 4)

	passwd = passwd + to64((int(ord(final[2:3])) << 16)
						   |(int(ord(final[8:9])) << 8)
						   |(int(ord(final[14:15]))), 4)

	passwd = passwd + to64((int(ord(final[3:4])) << 16)
						   |(int(ord(final[9:10])) << 8)
						   |(int(ord(final[15:16]))), 4)

	passwd = passwd + to64((int(ord(final[4:5])) << 16)
						   |(int(ord(final[10:11])) << 8)
						   |(int(ord(final[5:6]))), 4)

	passwd = passwd + to64((int(ord(final[11:12]))), 2)

	return magic + salt + b'$' + passwd

## assign a wrapper function:
md5crypt = unix_md5_crypt

if __name__ == "__main__":
	print( unix_md5_crypt("cat", "hat") )
