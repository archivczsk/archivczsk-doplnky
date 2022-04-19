# -*- coding: utf-8 -*-
#
#	   Copyright (C) 2015 tknorris (Derived from Mikey1234's & Lambda's)
#
#  This Program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2, or (at your option)
#  any later version.
#
#  This Program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with XBMC; see the file COPYING.  If not, write to
#  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
#  http://www.gnu.org/copyleft/gpl.html
#
#  This code is a derivative of the YouTube plugin for XBMC and associated works
#  released under the terms of the GNU General Public License as published by
#  the Free Software Foundation; version 3

import re
from time import sleep
from resolver import rslog

try:
	from urllib2 import urlopen, Request, HTTPError, URLError, HTTPCookieProcessor, build_opener, install_opener
	from urlparse import urlparse
	from urllib import quote
except:
	from urllib.request import urlopen, Request, HTTPCookieProcessor, build_opener, install_opener
	from urllib.parse import urlparse, quote
	from urllib.error import HTTPError, URLError

MAX_TRIES = 3
COMPONENT = __name__


class NoRedirection(HTTPErrorProcessor):

	def http_response(self, request, response):
		rslog.logDebug('Stopping Redirect')
		return response

	https_response = http_response


def solve_equation(equation):
	try:
		offset = (1 if equation[0] == '+' else 0)
		ev = equation.replace('!+[]', '1').replace('!![]',
				   '1').replace('[]', '0').replace('(', 'str(')[offset:]
		ev = re.sub(r'^str', 'float', re.sub(r'\/(.)str', r'/\1float', ev))
		return float(eval(ev))
	except:
		pass


def solve(url, cj, user_agent=None, wait=True):
	rslog.logDebug("CJ=%s"%cj)
	if user_agent is None:
		user_agent = util.UA
	headers = {'User-Agent': user_agent, 'Referer': url}
	if cj is not None:
		try:
			cj.load(ignore_discard=True)
		except:
			pass
		opener = build_opener(HTTPCookieProcessor(cj))
		install_opener(opener)

	scheme = urlparse(url).scheme
	domain = urlparse(url).hostname
	request = Request(url)
	for key in headers:
		request.add_header(key, headers[key])
	try:
		response = urlopen(request)
		html = response.read()
	except HTTPError as e:
		html = e.read()

	tries = 0
	while tries < MAX_TRIES:
		solver_pattern = \
			'var (?:s,t,o,p,b,r,e,a,k,i,n,g|t,r,a),f,\s*([^=]+)'
		solver_pattern += \
			'={"([^"]+)":([^}]+)};.+challenge-form\'\);'
		vc_pattern = \
			'input type="hidden" name="jschl_vc" value="([^"]+)'
		pass_pattern = 'input type="hidden" name="pass" value="([^"]+)'
		s_pattern = 'input type="hidden" name="s" value="([^"]+)'
		init_match = re.search(solver_pattern, html, re.DOTALL)
		vc_match = re.search(vc_pattern, html)
		pass_match = re.search(pass_pattern, html)
		s_match = re.search(s_pattern, html)

		if not init_match or not vc_match or not pass_match or not s_match:
			msg = \
				"[CF] Couldn't find attribute: init: |%s| vc: |%s| pass: |%s| No cloudflare check?"
			rslog.logDebug(msg % (init_match, vc_match, pass_match))
			return False

		(init_dict, init_var, init_equation) = \
			init_match.groups()
		vc = vc_match.group(1)
		password = pass_match.group(1)
		s = s_match.group(1)

		equations = re.compile(r"challenge-form\'\);\s*(.*)a.v").findall(html)[0]
		varname = (init_dict, init_var)
		result = float(solve_equation(init_equation.rstrip()))
		rslog.logDebug('[CF] Initial value: |%s| Result: |%s|' % (init_equation, result))

		for equation in equations.split(';'):
			equation = equation.rstrip()
			if len(equation) > len('.'.join(varname)):
				if equation[:len('.'.join(varname))] != '.'.join(varname):
					rslog.logDebug('[CF] Equation does not start with varname |%s|' % equation)
				else:
					equation = equation[len('.'.join(varname)):]

				expression = equation[2:]
				operator = equation[0]
				if operator not in ['+', '-', '*', '/']:
					rslog.logDebug('[CF] Unknown operator: |%s|' % equation)
					continue

				result = float(str(eval(str(result) + operator + str(solve_equation(expression)))))
				rslog.logDebug('[CF] intermediate: %s = %s' % (equation, result))
		
		result = '{0:.10f}'.format(eval('float({0} + {1})'.format(result, len(domain))))
		rslog.logDebug('[CF] Final Result: |%s|' % result)

		if wait:
			rslog.logDebug('Sleeping for 5 Seconds')
			sleep(5.1)

		url = \
			'%s://%s/cdn-cgi/l/chk_jschl?s=%s&jschl_vc=%s&pass=%s&jschl_answer=%s' \
			% (scheme, domain, quote(s), quote(vc), quote(password), quote(result))
		#rslog.logDebug('[CF] url: %s' % url)
		request = Request(url)
		for key in headers:
			request.add_header(key, headers[key])
		try:
			opener = build_opener(NoRedirection)
			install_opener(opener)
			response = urlopen(request)
			while response.getcode() in [301, 302, 303, 307]:
				if cj is not None:
					cj.extract_cookies(response, request)

				redir_url = response.info().getheader('location')
				rslog.logDebug("redirect_url=%s"%redir_url)
				if not redir_url.startswith('http'):
					base_url = '%s://%s' % (scheme, domain)
					redir_url = urlparse.urljoin(base_url, redir_url)
					rslog.logDebug("redirect_url=%s"%redir_url)

				request = Request(redir_url)
				for key in headers:
					request.add_header(key, headers[key])
				if cj is not None:
					cj.add_cookie_header(request)

				response = urlopen(request)
				rslog.logDebug("RESPONSE=\n%s"%response)
			final = response.read()
			
			if 'cf-browser-verification' in final:
				rslog.logDebug('[CF] Failure: html: %s url: %s' % (html, url))
				tries += 1
				html = final
			else:
				break
		except HTTPError as e:
			rslog.logDebug('[CF] HTTP Error: %s on url: %s' % (e.code, url))
			return False
		except URLError as e:
			rslog.logDebug('[CF] URLError Error: %s on url: %s' % (e, url))
			return False

	# cant call without param cache
	#if cj is not None:
	#	 util.cache_cookies()
	rslog.logDebug("FINAL=\n%s"%final)
	return final