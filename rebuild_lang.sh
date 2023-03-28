#!/bin/bash

if [ "$1" = "" ] ; then
	echo "Usage: $0 addon_directory"
	exit 1
fi

if [ -e /usr/bin/python3 ] ; then
	PY_CMD=python3
else
	PY_CMD=python
fi

ADDON="$1"
PY_FILES=$(find $ADDON -name '*.py')
LOCALE_DIR=${ADDON}/resources/language
mkdir -p $LOCALE_DIR

for lang in cs sk ; do
	# extract clean list of strings
	xgettext -L python $PY_FILES --no-wrap --foreign-user --package-name=$ADDON --package-version='' --copyright-holder='' -o ${LOCALE_DIR}/${lang}.pot
	sed -i 's/=CHARSET/=UTF-8/' ${LOCALE_DIR}/${lang}.pot

	# extract strings from settings
	echo "" >> ${LOCALE_DIR}/${lang}.pot
	$PY_CMD addon_settings2pot.py $ADDON >> ${LOCALE_DIR}/${lang}.pot
	
	# merge old translated strings to clean list
	if [ -e ${LOCALE_DIR}/${lang}.po ] ; then
		msguniq --no-wrap ${LOCALE_DIR}/${lang}.pot > ${LOCALE_DIR}/${lang}.pox
		mv ${LOCALE_DIR}/${lang}.pox ${LOCALE_DIR}/${lang}.pot
		msgmerge -U --no-wrap -N --backup=none --lang=${lang} ${LOCALE_DIR}/${lang}.po ${LOCALE_DIR}/${lang}.pot

		# remove clean strings file
		rm ${LOCALE_DIR}/${lang}.pot
	else
		mv ${LOCALE_DIR}/${lang}.pot ${LOCALE_DIR}/${lang}.po
	fi
	
done
