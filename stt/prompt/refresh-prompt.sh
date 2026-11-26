#!/bin/sh
# Rebuild /opt/voice/stt_prompt.txt in the voice LXC from Home Assistant's data. Runs on the Proxmox host,
# the one place that can reach both: HA (VM 111) holds the MA token and the title cache, LXC 113 the prompt.
# Nothing secret leaves the HA container: fetch_library.py prints names only.
#   install: cp fetch_library.py refresh-prompt.sh /usr/local/lib/stt-prompt/ on the host,
#            pct push 113 make_prompt.py /opt/voice/make_prompt.py, then enable stt-prompt.timer
set -eu
HERE=$(dirname "$(readlink -f "$0")")
qm guest exec 111 --timeout 60 --pass-stdin 1 -- docker exec -i homeassistant python3 - < "$HERE/fetch_library.py" \
  | python3 -c 'import json, sys
d = json.load(sys.stdin)
if d.get("exitcode"):
    sys.exit("fetch failed: " + d.get("err-data", "")[-500:])
print(d["out-data"])' \
  | pct exec 113 -- /opt/voice/venv/bin/python /opt/voice/make_prompt.py --out /opt/voice/stt_prompt.txt
