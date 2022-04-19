#!/bin/sh

case "$1" in
start)
        python /usr/lib/enigma2/python/Plugins/Extensions/archivCZSK/resources/repositories/addons/plugin.video.orangetv/orangetv_proxy.py &
        ;;
stop)
        kill -TERM `cat /tmp/orangetv_proxy.pid` 2> /dev/null
        rm -f /tmp/orangetv_proxy.pid
        ;;
restart|reload)
        $0 stop
        $0 start
        ;;
version)
        echo "1.0"
        ;;
info)
        echo "orangetv proxy"
        ;;
*)
        echo "Usage: $0 start|stop|restart"
        exit 1
        ;;
esac
exit 0
