#!/bin/zsh
# Install an APK on a Xiaomi device over adb, auto-tapping the "Install via USB" prompt
U=$1; APK=$2; D=$(dirname $0)
adb -s $U install -r -g "$APK" > $D/install.log 2>&1 &
for i in $(seq 30); do
  sleep 2
  grep -qE "Success|Failure" $D/install.log && break
  adb -s $U shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1
  b=$(adb -s $U shell cat /sdcard/ui.xml | python3 $D/ui.py '^Install$' | grep -oE '\[[0-9, ]+\]' | head -1 | tr -d '[] ')
  [ -n "$b" ] && { IFS=, read x1 y1 x2 y2 <<< "$b"; adb -s $U shell input tap $(( (x1+x2)/2 )) $(( (y1+y2)/2 )); }
done
wait; cat $D/install.log | tail -1
