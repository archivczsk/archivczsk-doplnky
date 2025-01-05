import sys

if sys.version[0] == '2':
	from urlparse import urlunparse, parse_qs, parse_qsl, urlparse, urljoin
	from urllib import quote, urlencode, quote_plus, unquote_plus, unquote
else:
	from urllib.parse import urlparse, urlunparse, urljoin, urlencode, parse_qs, parse_qsl, quote, quote_plus, unquote_plus, unquote
