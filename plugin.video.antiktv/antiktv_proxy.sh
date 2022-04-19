#!/bin/sh

case "$1" in
start)
        python /usr/lib/enigma2/python/Plugins/Extensions/archivCZSK/resources/repositories/addons/plugin.video.antiktv/antiktv_proxy.py &
        ;;
stop)
        kill -TERM `cat /tmp/antiktv_proxy.pid` 2> /dev/null
        rm -f /tmp/antiktv_proxy.pid
        ;;
restart|reload)
        $0 stop
        $0 start
        ;;
version)
        echo "1.0"
        ;;
info)
        echo "antiktv m3u8 proxy"
        ;;
*)
        echo "Usage: $0 start|stop|restart"
        exit 1
        ;;
esac
exit 0
