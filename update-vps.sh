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
CGO_ENABLED=0 go build -ldflags="-s -w" -o /usr/local/bin/dck-server ./server

mkdir -p /root/.dck-panel /root/.dck

cat > /etc/systemd/system/dck-panel.service << 'SYSTEMD'
[Unit]
Description=dck Panel
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/dck-server --port 80 --sftp-port 2222 --data-dir /root/.dck-panel
Restart=always
RestartSec=5
Environment=HOME=/root
Environment=JWT_SECRET=my_fixed_secret_key_32_char_long
Environment=ADMIN_PASSWORD=admin123

[Install]
WantedBy=multi-user.target
SYSTEMD

systemctl daemon-reload

if systemctl is-active --quiet dck-panel 2>/dev/null; then
  systemctl restart dck-panel
  echo "dck-panel restarted via systemd"
elif systemctl is-active --quiet dck-server 2>/dev/null; then
  systemctl stop dck-server 2>/dev/null || true
  systemctl enable --now dck-panel
  echo "migrated from dck-server to dck-panel service"
else
  systemctl enable --now dck-panel
  echo "dck-panel started via systemd"
fi

echo ""
echo "=== Done ==="
dck blueprint list | head -5
