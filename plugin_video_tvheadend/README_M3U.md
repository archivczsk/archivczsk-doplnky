# plugin.video.tvheadend v0.14

Klient pre Tvheadend DVR server s podporou externého M3U playlistu a XMLTV EPG.

## Čo je nové v 0.14

Pridaný externý M3U zdroj ako paralelný bouquet s **podporou DVB titulkov**
(použitím "fake DVB" service refov type=1).

## Inštalácia

Skopíruj celý priečinok do:
```
/usr/lib/enigma2/python/Plugins/Extensions/archivCZSK/resources/repositories/<repo>/plugin.video.tvheadend/
```

Reštartuj enigma2:
```
init 4 && sleep 1 && init 3
```

## Použitie M3U zdroja

1. Plugins → ArchivCZSK → Tvheadend → Setup
2. Nový tab "External M3U Playlist"
3. Zaškrtni "Enable external M3U playlist source"
4. Vyplň M3U URL (+ voliteľne HTTP auth a XMLTV EPG URL)
5. Service type nechaj na "1 - Native DVB" → DVB titulky budú fungovať
6. Save → po pár sekundách sa objaví nový bouquet "IPTV M3U"

## Mapping override XML (sort/rename/disable)

Vytvor `/etc/enigma2/m3u-sort-override.xml` v rovnakom formáte ako
e2m3u2bouquet override (príklad v `docs/example_mapping.xml`) a zaškrtni
"Use mapping override XML" v settings.

## Súbory M3U modulu

- `m3u_provider.py` — M3U + XMLTV fetcher/parser
- `m3u_bouquet.py` — bouquet writer (type=1 refy, picon downloader, epgimport export)
- `m3u_mapping.py` — loader pre override XML
- `m3u_manager.py` — orchestrátor + scheduler

## Koexistencia s TVH zdrojom

Oba zdroje môžu bežať súčasne. TVH generuje `userbouquet.tvheadend_*.tv`,
M3U generuje `userbouquet.m3u_iptv.tv`. Žiadne kolízie v piconoch (TSID/ONID
sú deterministické per-category hash).
