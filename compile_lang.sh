#!/bin/sh

if [ "$1" = "clean" ] ; then
	do_clean=1
else
	do_clean=0
fi

find -name '*.po' | while read line ; do
	lang=`basename $line .po`
	lng_dir=`dirname $line`
	addon_dir=`echo $lng_dir | cut -d '/' -f -2`
	addon_id=`./get_addon_attribute $addon_dir/addon.xml id`

	if [ $do_clean = 1 ] ; then
		if [ -f $lng_dir/$lang/LC_MESSAGES/${addon_id}.mo ] ; then
			rm $lng_dir/$lang/LC_MESSAGES/${addon_id}.mo
			rmdir $lng_dir/$lang/LC_MESSAGES
			rmdir $lng_dir/$lang
		fi
	else
		echo "Compiling $lang lang for $addon_id"
		mkdir -p $lng_dir/$lang/LC_MESSAGES
		msgfmt $line -o $lng_dir/$lang/LC_MESSAGES/${addon_id}.mo
	fi
done
