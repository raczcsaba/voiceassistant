#!/bin/zsh
# Re-enable everything disabled on 2026-11-13
while read p; do adb shell pm enable --user 0 $p; done < "$(dirname $0)/disabled-packages.txt"
