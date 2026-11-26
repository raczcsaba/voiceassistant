#!/bin/sh
# Copy the code and config.json to the server and restart the service.
# TARGET is a command that runs a shell on the server, reading stdin, for example:
#   TARGET="ssh root@voice-host" ./deploy.sh
#   TARGET="ssh pve-host pct exec <ctid> --" ./deploy.sh   (a Proxmox LXC)
set -e
cd "$(dirname "$0")"
: "${TARGET:?set TARGET to a command that runs a shell on the server}"
DEST=${DEST:-/opt/voice/claude}
COPYFILE_DISABLE=1 tar czf - --exclude __pycache__ --exclude data --exclude config.json \
    voice_claude tests requirements.txt config.example.json voice-claude.service | base64 > /tmp/voice-claude.b64
{
  echo "set -e; mkdir -p $DEST/app.new $DEST/data"
  echo "base64 -d > /tmp/voice-claude.tgz <<'__EOF__'"; cat /tmp/voice-claude.b64; echo "__EOF__"
  echo "tar xzf /tmp/voice-claude.tgz -C $DEST/app.new && rm /tmp/voice-claude.tgz"
  if [ -f config.json ]; then
    echo "cat > $DEST/config.json <<'__EOF__'"; cat config.json; echo; echo "__EOF__"; echo "chmod 600 $DEST/config.json"
  fi
  echo "rm -rf $DEST/app && mv $DEST/app.new $DEST/app"
  echo "cp $DEST/app/voice-claude.service /etc/systemd/system/ && systemctl daemon-reload"
  echo "systemctl restart voice-claude 2>/dev/null || true"
} | $TARGET sh -s
rm -f /tmp/voice-claude.b64
echo deployed
