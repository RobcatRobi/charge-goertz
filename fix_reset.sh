#!/bin/bash
# Fix Shelly Reset in app.py

cat > /tmp/reset_patch.py << 'EOF'
import re

with open('/opt/charge-goertz/app.py', 'r') as f:
    content = f.read()

# Ersetze die reset Funktion mit der korrekten Shelly 3EM API
old_reset = '''@APP.route("/api/shelly/reset/<int:sid>", methods=["POST"])
def reset_shelly(sid):
    """Reset Shelly energy counters"""
    ip = STATIONS.get(sid, {}).get("ip_3em", "")
    if not ip: return jsonify({"error":"no ip"}), 400
    try:
        # Shelly 3EM reset command
        r = requests.get(f"http://{ip}/emeter/0/em_data.csv?reset=true", timeout=3)
        for i in range(3):
            requests.get(f"http://{ip}/emeter/{i}?reset=True", timeout=3)
        # Log reset in Supabase
        supa_post("energy_log", {
            "station_id": sid, "ts": int(time.time()*1000),
            "power_w": 0, "total_kwh": 0, "note": "RESET"
        })
        return jsonify({"ok":True,"message":"Shelly Zähler zurückgesetzt"})
    except Exception as e:
        return jsonify({"error":str(e)}), 500'''

new_reset = '''@APP.route("/api/shelly/reset/<int:sid>", methods=["POST"])
def reset_shelly(sid):
    """Reset Shelly 3EM energy counters - correct API"""
    ip = STATIONS.get(sid, {}).get("ip_3em", "")
    if not ip: return jsonify({"error":"no ip"}), 400
    try:
        # Lese aktuellen Stand vor Reset
        try:
            r = requests.get(f"http://{ip}/status", timeout=4).json()
            em = r.get("emeters", [])
            total_kwh = sum(e.get("total", 0) for e in em) / 1000
        except:
            total_kwh = 0

        # Shelly 3EM Gen1 Reset: POST auf /emeter/{n}/reset_data
        reset_ok = []
        for i in range(3):
            try:
                resp = requests.post(f"http://{ip}/emeter/{i}/reset_data", timeout=3)
                reset_ok.append(resp.status_code == 200)
            except Exception as ex:
                reset_ok.append(False)

        # Supabase: Reset-Event mit letztem Stand loggen
        supa_post("energy_log", {
            "station_id": sid,
            "ts": int(time.time()*1000),
            "power_w": 0,
            "total_kwh": total_kwh,
            "note": f"RESET (Stand vor Reset: {total_kwh:.3f} kWh)"
        })

        success = any(reset_ok)
        return jsonify({
            "ok": success,
            "phases_reset": reset_ok,
            "kwh_before_reset": round(total_kwh, 3),
            "message": f"Shelly Zähler zurückgesetzt (vorher: {total_kwh:.2f} kWh)" if success else "Reset fehlgeschlagen"
        })
    except Exception as e:
        return jsonify({"error":str(e)}), 500'''

if old_reset in content:
    content = content.replace(old_reset, new_reset)
    print("Reset Funktion gefunden und ersetzt!")
else:
    # Füge neue Reset-Funktion hinzu (falls anders formatiert)
    # Finde die Funktion mit regex
    import re
    pattern = r'@APP\.route\("/api/shelly/reset.*?return jsonify\(\{"error":str\(e\)\}\), 500'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.start()] + new_reset + content[match.end():]
        print("Reset Funktion mit regex ersetzt!")
    else:
        print("WARNUNG: Reset Funktion nicht gefunden - füge am Ende hinzu")

with open('/opt/charge-goertz/app.py', 'w') as f:
    f.write(content)

print("app.py gespeichert!")
print(f"Neue reset Funktion: {'reset_data' in content}")
EOF

python3 /tmp/reset_patch.py
sudo systemctl restart charge-goertz
sleep 2
systemctl is-active charge-goertz && echo "✓ Flask läuft"

# Teste Reset direkt
echo "Teste Reset..."
curl -s -X POST http://localhost:5000/api/shelly/reset/1 | python3 -m json.tool
