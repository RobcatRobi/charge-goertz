#!/bin/bash
set -e
echo "═══════════════════════════════════════"
echo "  ChargeGörtz v11 — Pi Install Script"
echo "═══════════════════════════════════════"
WEBDIR=/opt/charge-goertz/web
APPDIR=/opt/charge-goertz

# 1. index.html
echo "→ index.html..."
sudo curl -sL "https://raw.githubusercontent.com/RobcatRobi/charge-goertz/main/index.html" \
  -o $WEBDIR/index.html
echo "  ✓ $(wc -c < $WEBDIR/index.html) bytes"

# 2. Service Worker
echo "→ sw.js..."
sudo curl -sL "https://raw.githubusercontent.com/RobcatRobi/charge-goertz/main/sw.js" \
  -o $WEBDIR/sw.js
echo "  ✓ sw.js"

# 3. Push Daemon installieren
echo "→ push_daemon.py..."
sudo curl -sL "https://raw.githubusercontent.com/RobcatRobi/charge-goertz/main/push_daemon.py" \
  -o $APPDIR/push_daemon.py

# 4. Push Daemon als Systemd Service
sudo tee /etc/systemd/system/cg-push.service > /dev/null << 'EOF'
[Unit]
Description=ChargeGörtz Push Daemon
After=network.target charge-goertz.service
Requires=charge-goertz.service

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/charge-goertz
ExecStart=/usr/bin/python3 /opt/charge-goertz/push_daemon.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable cg-push
sudo systemctl restart cg-push
sudo systemctl restart charge-goertz

echo ""
echo "Status:"
systemctl is-active charge-goertz && echo "✓ Flask läuft" || echo "❌ Flask"
systemctl is-active cg-push && echo "✓ Push Daemon läuft" || echo "❌ Push Daemon"
echo ""
echo "✅ Installation abgeschlossen!"
echo "   App: http://192.168.3.103:8080"
