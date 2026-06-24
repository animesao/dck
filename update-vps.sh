#!/bin/bash
set -e

echo "=== Updating dck CLI ==="
cd /tmp
rm -rf dck-update
git clone https://github.com/animesao/dck.git dck-update
cd dck-update
CGO_ENABLED=0 go build -ldflags="-s -w" -o dck .
pkill -f "dck " 2>/dev/null || true
cp dck /usr/local/bin/dck
rm -rf /tmp/dck-update
echo "dck updated: $(dck version)"

echo ""
echo "=== Updating dck-panel ==="
cd /opt/dck-panel
git fetch origin
git reset --hard origin/main
CGO_ENABLED=0 go build -o /usr/local/bin/dck-server ./server

if command -v systemctl &> /dev/null && systemctl is-active --quiet dck-server 2>/dev/null; then
  systemctl restart dck-server
  echo "dck-server restarted via systemd"
else
  pkill dck-server 2>/dev/null || true
  nohup /usr/local/bin/dck-server > /var/log/dck-panel.log 2>&1 &
  echo "dck-server restarted (no systemd)"
fi

echo ""
echo "=== Done ==="
dck blueprint list | head -5
