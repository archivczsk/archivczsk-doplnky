#!/bin/bash

TOOLS=$(dirname "$0")

if [ -e /usr/bin/python3 ] ; then
	PY_CMD=python3
else
	PY_CMD=python
fi

BUILD_DIR=repo
echo "Cleaning up .pyc .pyo and __pycache__ files/dirs ..."
find . -name '*.pyc' | xargs rm -f
find . -name '*.pyo' | xargs rm -f
find . -name __pycache__ | xargs rm -rf

if [ -z $1 ];
then
	addons=$(ls -l | grep "^d" | gawk -F' ' '{print $9}')
else
	addons=$1
fi

for addonFile in $addons ; do
    dirname=$addonFile
    if [ ! -f $addonFile/addon.xml ] ; then
	#echo "$addonFile/addon.xml does not exist, skipping"
	continue
    fi
    addon_id=$($PY_CMD "$TOOLS/get_addon_attribute" "$addonFile/addon.xml" "id")
    addon_version=$($PY_CMD "$TOOLS/get_addon_attribute" "$addonFile/addon.xml" "version")

    if [ -z "$addon_id" ] ; then
        echo "Addon id not found!" >&2
        exit 1
    fi

    if [ -z "$addon_version" ] ; then
        echo "Addon id not found!" >&2
        exit 2
    fi
    # generate current hash and check for saved values 
    md5=`echo $(find $addon_id -type f | xargs md5sum | md5sum | tr -d -)`
    if [ ! -f hashes/$addon_id ];then
      echo "$addon_id was never released!"
      continue
    fi
    need=$(grep -c $md5 hashes/$addon_id)
    if [ "$need" == "0" ]; then
      echo "Addon $addon_id"
      echo " needs release $needs"
      target_dir="$BUILD_DIR/$addon_id"
      package="$target_dir/$addon_id-$addon_version.zip"
      if [ -e "$package" ] ; then
         echo " needs version bump from $addon_version"
      fi
    fi
    continue
done
