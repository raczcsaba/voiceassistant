#!/bin/zsh
# Re-enable everything disabled on the tablet on 2026-11-22
while read p; do adb -s f9cea3e6 shell pm enable --user 0 $p; done < "$(dirname $0)/disabled-packages.txt"
