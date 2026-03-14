#!/bin/bash
# ChargeGörtz — Cloudflare Tunnel Setup
# KEIN Account nötig für Quick Tunnel!
echo "╔══════════════════════════════════════════╗"
echo "║  ChargeGörtz — Cloudflare Tunnel Setup   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 1. cloudflared installieren
echo "→ Installiere cloudflared..."
if command -v cloudflared &> /dev/null; then
  echo "  ✓ cloudflared bereits installiert"
else
  curl -L "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64" \
    -o /tmp/cloudflared 2>/dev/null
  sudo install /tmp/cloudflared /usr/local/bin/cloudflared
  echo "  ✓ cloudflared installiert"
fi

cloudflared --version

# 2. Systemd Service erstellen (startet automatisch beim Boot)
echo ""
echo "→ Erstelle cloudflared Service..."
sudo tee /etc/systemd/system/cloudflared-cg.service > /dev/null << 'SVCEOF'
[Unit]
Description=ChargeGörtz Cloudflare Tunnel
After=network.target charge-goertz.service

[Service]
Type=simple
User=pi
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:8080 --no-autoupdate
Restart=always
RestartSec=10
StandardOutput=append:/var/log/cloudflared-cg.log
StandardError=append:/var/log/cloudflared-cg.log

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable cloudflared-cg
sudo systemctl restart cloudflared-cg

echo "  ✓ Service gestartet"
echo ""
echo "→ Warte auf Tunnel URL (15 Sekunden)..."
sleep 15

# 3. URL aus Log lesen
URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/cloudflared-cg.log | tail -1)

if [ -z "$URL" ]; then
  # Nochmal versuchen
  sleep 10
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/cloudflared-cg.log | tail -1)
fi

echo ""
echo "╔══════════════════════════════════════════╗"
if [ -n "$URL" ]; then
  echo "║  ✓ TUNNEL AKTIV!                         ║"
  echo "║                                          ║"
  echo "║  URL: $URL"
  echo "║                                          ║"
  echo "║  Von ÜBERALL erreichbar ohne VPN!        ║"
  echo "╚══════════════════════════════════════════╝"
  # URL in Datei speichern damit App sie lesen kann
  echo "$URL" | sudo tee /opt/charge-goertz/tunnel_url.txt > /dev/null
  echo ""
  echo "→ Aktualisiere Flask damit URL bekannt ist..."
  sudo systemctl restart charge-goertz
else
  echo "║  ⚠ URL noch nicht verfügbar             ║"  
  echo "║  Prüfe Log:                              ║"
  echo "║  sudo tail /var/log/cloudflared-cg.log   ║"
  echo "╚══════════════════════════════════════════╝"
fi

echo ""
echo "Status:"
systemctl is-active cloudflared-cg && echo "✓ Tunnel läuft" || echo "❌ Tunnel Fehler"
systemctl is-active charge-goertz && echo "✓ Flask läuft" || echo "❌ Flask Fehler"
echo ""
echo "Log anzeigen: sudo tail -f /var/log/cloudflared-cg.log"
