#!/bin/bash
# Füge /api/tunnel zu Flask hinzu + zeige Tunnel URL

# Patch Flask app.py
python3 << 'PYEOF'
with open('/opt/charge-goertz/app.py','r') as f: c=f.read()
if '/api/tunnel' not in c:
    patch = '''
@APP.route("/api/tunnel")
def tunnel_url():
    import subprocess
    try:
        with open("/opt/charge-goertz/tunnel_url.txt") as f:
            url = f.read().strip()
        if url:
            return __import__('flask').jsonify({"url":url,"active":True})
    except: pass
    # Versuche aus Log zu lesen
    try:
        r = subprocess.run(['grep','-o','https://[a-z0-9-]*.trycloudflare.com',
            '/var/log/cloudflared-cg.log'], capture_output=True, text=True)
        urls = r.stdout.strip().split('\\n')
        url = [u for u in urls if u][-1] if urls else ''
        if url:
            with open("/opt/charge-goertz/tunnel_url.txt","w") as f: f.write(url)
            return __import__('flask').jsonify({"url":url,"active":True})
    except: pass
    return __import__('flask').jsonify({"url":None,"active":False})
'''
    c = c + patch
    with open('/opt/charge-goertz/app.py','w') as f: f.write(c)
    print("✓ /api/tunnel hinzugefügt")
else:
    print("✓ /api/tunnel bereits vorhanden")
PYEOF

# Flask neu starten
sudo systemctl restart charge-goertz
sleep 2

# Tunnel URL aus Log lesen
echo ""
echo "=== CLOUDFLARE TUNNEL URL ==="
URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/cloudflared-cg.log 2>/dev/null | tail -1)

if [ -n "$URL" ]; then
    echo "✅ URL GEFUNDEN:"
    echo ""
    echo "  $URL"
    echo ""
    echo "  → Von ÜBERALL erreichbar!"
    echo "$URL" > /opt/charge-goertz/tunnel_url.txt
else
    echo "Kein Log gefunden. Service Status:"
    systemctl status cloudflared-cg --no-pager | head -20
fi

echo ""
echo "Service Status:"
systemctl is-active cloudflared-cg && echo "✅ Tunnel Service läuft" || echo "⚠ Service nicht aktiv"
systemctl is-active charge-goertz && echo "✅ Flask läuft" || echo "❌ Flask"
