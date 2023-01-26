#-*- coding: utf-8 -*-
#------------------------------------------------------------
# pelisalacarta - XBMC Plugin
# Utilidades para detectar v�deos de los diferentes conectores
# http://blog.tvalacarta.info/plugin-xbmc/pelisalacarta/
#
# Modify: 2012-07-31, Ivo Brhel
#
#------------------------------------------------------------
import re


debug = False
#debug = True

def findvideo(data):
	seznam = set()
	adresy = []

	if debug: 
		print("8) Youtube ...")
	pattern	 = '<iframe.*src="(http://www.youtube.com/embed/[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Youtube"
		url = match

		if url not in seznam:
			print("8) Youtube  url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)


	if debug: 
		print("1a) Movshare ...")
	pattern	 = '"(http://www.movshare.net/video/[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)
	
	for match in matches:
		server = "Movshare"
		url = match
		if url not in seznam:
			print("1a) Movshare	 url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)

	if debug: 
		print("1b) Movshare ...")
	pattern	 = "'(http://www.movshare.net/embed/[^']+)"
	matches = re.compile(pattern,re.DOTALL).findall(data)
	
	for match in matches:
		server = "Movshare"
		url = match
		if url not in seznam:
			print("1b) Movshare	 url="+url)
			adresy.append( [ server , url ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)



	if debug: 
		print("1c) Movshare ...")
		pattern	 = "'(http://www.movshare.net/embed/[^']+)'"
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Movshare"
		url = match

		if url not in seznam:
			print("1c) Movshare	 url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)


	if debug: 
		print("1d) Movshare ...")
	pattern	 = "<iframe.*src='(http://embed.movshare.net/embed.php\?[^']+)"
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Movshare"
		url = match

		if url not in seznam:
			print("1d) Movshare	 url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)

			
	if debug: 
		print("2a) Videoweed ...")
	pattern	 = '(http://www.videoweed.com/file/*?\.flv)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Videoweed"
		url = match

		if url not in seznam:
			print("2a) Videoweed  url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)

	if debug: 
		print("2b) Videoweed ...")
	pattern	 = '(/videoweed.php\?id=.*?[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Videoweed"
		url = match

		if url not in seznam:
			print("2b) Videoweed  url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)
	

	if debug: 
		print("3a) Videobb ...")
	pattern	 = '(http://www.videobb.com/e/.*?[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Videobb"
		url = match

		if url not in seznam:
			print("3a) Videobb	url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)
	
	if debug: 
		print("3b) Videobb ...")
	pattern	 = '(http://videobb.com/e/.*?[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Videobb"
		url = match

		if url not in seznam:
			print("3b) Videobb	url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)

	
	if debug: 
		print("4a) Videozer ...")
	pattern	 = '(http://www.videozer.com/embed/.*?[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Videozer"
		url = match

		if url not in seznam:
			print("4a) Videozer	 url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)
	
	if debug: 
		print("4b) Videozer ...")
	pattern	 = '(http://videozer.com/embed/.*?[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Videozer"
		url = match

		if url not in seznam:
			print("4b) Videozer	 url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)
	
	
	if debug: 
		print("5) Novacz ...")
	pattern	 = 'http://archiv.nova.cz/static/cz/shared/app/MediaCenter_Catchup.swf'
	matches = re.compile(pattern,re.DOTALL).findall(data)
	if len(matches) >0:

		pattern = '<param name=\"flashVars\" .*/.*<embed'
		matches = re.compile(pattern,re.DOTALL).findall(data)

		for match in matches:
			server = "Novacz"
			url = match

			if url not in seznam:
				mediaid = re.compile('media_id=(.+?)&').findall(url)
				siteid = re.compile('site_id=(.+?)&').findall(url)
				url = 'media_id='+mediaid[0]+'|site_id='+siteid[0]

				print("5) Novacz  url="+url)
				adresy.append( [ server , url  ] )
				seznam.add(url)
			else:
				print("	 url duplicate="+url)
	
	if debug: 
		print("6a) Novamov ...")
	pattern	 = '(/novamov.php\?id=[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Novamov"
		url = match

		if url not in seznam:
			print("6a1) Novamov	 url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)
	
	if debug: 
		print("6b) Novamov ...")
	pattern	 = 'mce_src="(http://embed.novamov.com/embed.php\?[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Novamov"
		url = match

		if url not in seznam:
			print("6b) Novamov	url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)
	

	if debug: 
		print("6c) Novamov ...")
	pattern	 = 'mce_href="(http://www.novamov.com/video/[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Novamov"
		url = match

		if url not in seznam:
			print("6c) Novamov	url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)

	if debug: 
		print("6d) Novamov ...")
	pattern	 = "src=['|\"](http://embed.novamov.com/embed.php\?[^'|^\"]+)"
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Novamov"
		url = match

		if url not in seznam:
			print("6d) Novamov	url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)


	if debug: 
		print("7a) VK ...")
	pattern	 = 'src="(http://vk.com/video_ext.php\?oid[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "VK"
		url = match

		if url not in seznam:
			print("7a) VK  url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)
	
	if debug: 
		print("7b) VK ...")
	pattern	 = 'mce_src="(http://vkontakte.ru/video_ext.php\?oid[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "VK"
		url = match

		if url not in seznam:
			print("7b) VK  url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)
	

	if debug: 
		print("9a) Putlocker ...")
	pattern	 = 'href="(/putlocker.php\?id=[^"]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Putlocker"
		url = match

		if url not in seznam:
			print("9a) Putlocker  url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)


	if debug: 
		print("9b) Putlocker ...")
	pattern	 = '<iframe.*src=.*(http://www.putlocker.com/embed/[^"|\&]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Putlocker"
		url = match

		if url not in seznam:
			print("9b) Putlocker  url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)



	if debug: 
		print("10a) Stagevu ...")
		pattern	 = '(http://stagevu.com/video/[A-Z0-9a-z]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Stagevu"
		url = match

		if url not in seznam:
			print("10a) Stagevu	 url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)


	if debug: 
		print("10b) Stagevu ...")
		pattern	 = 'http://stagevu.com.*?uid\=([A-Z0-9a-z]+)'
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Stagevu"
		url = "http://stagevu.com/video/"+match

		if url not in seznam:
			print("10b) Stagevu	 url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)


	if debug: 
		print("11) Ulozto ...")
	pattern	 = "<a class=\"under\".*href=\"(.+?)[^\"]\".*>(.+?)[^<]</a></abbr"
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Ulozto"
		url = match[0]

		if url not in seznam:
			print("11) Ulozto  url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)


	if debug: 
		print("12) Stagero.eu ...")
	pattern	 = "iframe.*src=\"(http://embed.stagero.eu/embed\.php\?v.+?)&"
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Stagero"
		url = match

		if url not in seznam:
			print("12) Stagero	url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)


	if debug: 
		print("13) Vidxden/Vidbux ...")
	pattern	 = "href=/(vidxden)\.php?id=(.+?)\""
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Vidxden"
		url = match

		if url not in seznam:
			print("13) Vidxden	url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)

	if debug: 
		print("14) Servertip ...")
	pattern	 = "href=\"(/servertip.php\?id=.+?)\"" 
	matches = re.compile(pattern,re.DOTALL).findall(data)

	for match in matches:
		server = "Servertip"
		url = match

		if url not in seznam:
			print("14) Servertip  url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)


	if debug: 
		print("15) 24video ...")
	pattern	 = "rootUrl=http://www.24video.net" 
	matches = re.compile(pattern,re.DOTALL).findall(data)
	
	if len(matches) >0:

		pattern = 'flash[v|V]ars.*\"id=(.+?)&amp;idHtml=(.+?)&amp;.*rootUrl=(.+?)&amp;'
		matches = re.compile(pattern,re.DOTALL).findall(data)

		for match in matches:
			server = "24video"
			url = match

			if url not in seznam:
				vid	 = match[0]
				vhtml= match[1]
				vurl = match[2]
				
				
				url = ('%s%s%s?mode=play'% (vurl , vhtml,vid))

				print("15) 24Video	url="+url)
				adresy.append( [ server , url  ] )
				seznam.add(url)
			else:
				print("	 url duplicate="+url)


	if debug: 
		print("16) IFRAME ...")
	pattern	 = "<iframe.+?src=[\"|'](/iframe/iframe.php\?id=.+?)['|\"]" 
	matches = re.compile(pattern,re.DOTALL).findall(data)
	
	for match in matches:
		server = "IFrame"
		url = match

		if url not in seznam:
			print("16) IFRAME  url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)
	

	
	if debug: 
		print("17) VIDEOMAIL ...")
	pattern = '<param name="flashvars".+?value="(movieSrc=.+?)"'
	matches = re.compile(pattern,re.DOTALL).findall(data)
	print(matches)
	
	for match in matches:
		server = "Videomail"
		url = match

		if url not in seznam:
			print("16) VIDEOMAIL  url="+url)
			adresy.append( [ server , url  ] )
			seznam.add(url)
		else:
			print("	 url duplicate="+url)
	

	return adresy