# archivczsk-doplnky
Doplňky pro archivczsk Enigma2 plugin.

Tyto doplňky neposkytují žádný obsah, jen simulují prohlížeč veřejně dostupné web stránky resp. android/ios aplikace. Žádný z autorů jednotlivých doplňků není zodpovědný za obsah, který tato stránka/aplikace poskytuje.

## Podpora
Ak máte problém, tak podporu môžete hľadať na fórach ako napr. **CS Fórum** https://cs-forum.eu/viewtopic.php?t=13

## Info pokiaľ vám nefunguje SCC
Pokiaľ vám nefunguje SCC, tzn. vypisuje to hlášku, že vypršal časový limit pripojenia, server vrátil chybový kód 522 a podobne, tak problém je na strane SCC serverov. Je nutné skontrolovať, že v nastaveniach doplnku máte zvolený protokol pre komunikáciu s API na HTTPS. Z dôvodu chyby na strane SCC komunikácia cez HTTP protokol nefunguje. Pre správnu funkčnosť komunikácie cez HTTPS potrebujete mať aktualizované image (ktoré pravidelne dostáva aktualizácie) ako napr OpenATV >= 7.2, OpenPLi >= 8.3 a pod. Neaktualizované image ako napr. VTi majú neaktuálne TLS certifikáty a preto HTTPS pre SCC nefunguje.
