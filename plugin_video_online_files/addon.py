# -*- coding: utf-8 -*-

from Plugins.Extensions.archivCZSK.engine import client

def run(addon, session, params):
	client.showInfo("Vývoj a údržba doplnku skončili a doplnok viac už nie je funkčný. Náhradou je nový doplnok Webshare.cz")

def main(addon):
	return run
