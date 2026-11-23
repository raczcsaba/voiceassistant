#!/bin/zsh
# Bring back the Xiaomi system apps removed for user 0 on 2026-11-22
while read p; do adb -s f9cea3e6 shell cmd package install-existing $p; done < "$(dirname $0)/removed-for-user0.txt"
