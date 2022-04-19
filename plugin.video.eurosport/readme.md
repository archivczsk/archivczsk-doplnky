For fully working plugin you need to obtain the "st" cookie value from your browser.

- Open Google Chrome browser
- Log into www.eurosportplayer.com and start play any video
- Press F12 to access developer tools
- Select Application tab
- On the left hand side of the popup select Cookies in the Storage section.
- Locate the 'st' cookie Name under https://www.eurosportplayer.com and copy it's Value.
- Close browser without Logout! If you logout, the cookie expires! Better to use annonymous browser window
- Save value of st cookie to file named cookie
- FTP upload this file to Enigma box to /usr/lib/enigma2/python/Plugins/Extensions/archivCZSK/resources/data/plugin.video.eurosport/cookie
- If directory /usr/lib/enigma2/python/Plugins/Extensions/archivCZSK/resources/data/plugin.video.eurosport does not exit, create it

You do not need to stop/start Enigma2.

=============
CESKA VERZE:
=============

Pro spravnou funkci doplnku je treba ziskat 'st' cookie z prohlizece.

- Otevrete prohlizec Google Chrome
- Prihlaste se na strance www.eurosportplayer.com a spustte jakekoliv video
- Stisknete klavesu F12
- Otevre se okno, ve kterem vyberte zalozku Application (Aplikace)
- Na leve strane otevrete Cookies a v nem kliknete na https://www.eurosportplayer.com
- Najdete vpravo jmeno (Name) 'st' a zkopirujte si jeho hodnotu (Value), bude to hodne dlouhy retezec zacinajici vetsinou ey...
- Zavrete prohlizec bez odhlasovani z webu! Pokud se odhlasite, ztrati cookie platnost! Nejlepe pouzijte anonymni okno prohlizece
- Zkopirovanou hodnotu ulozte do souboru 'cookie'
- Tento soubor zkopirujte do boxu do slozky /usr/lib/enigma2/python/Plugins/Extensions/archivCZSK/resources/data/plugin.video.eurosport
- Pokud tato slozka neexistuje, vytvorte ji a vlozte do ni soubor cookie

Nyni by jiz melo fungovat prehravani. Neni treba znovu restartovat box.
