# -*- coding: utf-8 -*-

from Plugins.Extensions.archivCZSK.engine import client

def run(addon, session, params):
	client.showInfo("Tento doplnok využíval službu od O2 ktorá skončila a preto doplnok viac nie je funkčný. Náhradou je nový doplnok O2 TV 2.0.")

def main(addon):
	return run
