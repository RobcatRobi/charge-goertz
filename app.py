import time, requests, hashlib, os, threading
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

APP = Flask(__name__, static_folder="/opt/charge-goertz/web")
CORS(APP, origins="*")

SUPA_URL = "https://vloululxbazfcvlhmtzr.supabase.co"
SUPA_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZsb3VsdWx4YmF6ZmN2bGhtdHpyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMxNDEyOTcsImV4cCI6MjA4ODcxNzI5N30.pUrwkI2g2DpA7q7o0cSEWzXGeUiJxO74TdLj7iEd3N8"
SUPA_HDR = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}", "Content-Type": "application/json"}

STATIONS = {
    1: {"ip_3em": "192.168.3.223", "ip_mini": "192.168.3.224", "tariff": 0.25, "name": "Neerach"},
    2: {"ip_3em": "",              "ip_mini": "",               "tariff": 0.25, "name": "Brail"},
}

# ── AUTO-STOP STATE ──────────────────────────────────────────
_low_power_since = {}   # {station_id: timestamp_seit_niedrig}
LOW_POWER_THRESHOLD = 0.2   # kW
LOW_POWER_DURATION  = 60    # Sekunden

def supa_get(table, params=""):
    try:
        r = requests.get(f"{SUPA_URL}/rest/v1/{table}?{params}", headers=SUPA_HDR, timeout=5)
        return r.json() if r.ok else []
    except: return []

def supa_post(table, data):
    try:
        r = requests.post(f"{SUPA_URL}/rest/v1/{table}",
            headers={**SUPA_HDR, "Prefer": "return=representation"}, json=data, timeout=5)
        return r.json() if r.ok else None
    except: return None

def supa_patch(table, filt, data):
    try:
        r = requests.patch(f"{SUPA_URL}/rest/v1/{table}?{filt}",
            headers={**SUPA_HDR, "Prefer": "return=representation"}, json=data, timeout=5)
        return r.ok
    except: return False

def supa_delete(table, filt):
    try:
        requests.delete(f"{SUPA_URL}/rest/v1/{table}?{filt}", headers=SUPA_HDR, timeout=5)
        return True
    except: return False

# ── AUTO-STOP BACKGROUND THREAD ──────────────────────────────
def auto_stop_loop():
    """Alle 15s: prüft ob Leistung < 0.2kW für 60s → Session stoppen"""
    time.sleep(20)  # Warte beim Start bis alles bereit ist
    while True:
        try:
            for sid, st in STATIONS.items():
                if not st["ip_3em"]:
                    continue
                # Aktive Session (stopped_at = null)
                sessions = supa_get("sessions",
                    f"select=id,user_id,started_at,kwh,tariff,start_total_kwh"
                    f"&station_id=eq.{sid}&stopped_at=is.null"
                    f"&order=started_at.desc&limit=1")
                if not sessions:
                    _low_power_since.pop(sid, None)
                    continue
                sess = sessions[0]
                # Shelly Leistung holen
                try:
                    r = requests.get(f"http://{st['ip_3em']}/status", timeout=4).json()
                    em = r.get("emeters", [])
                    total_w = r.get("total_power", sum(e.get("power", 0) for e in em))
                    total_kwh = round(sum(e.get("total", 0) for e in em) / 1000, 3)
                    power_kw = total_w / 1000
                except Exception as e:
                    print(f"[AutoStop] Shelly {sid} nicht erreichbar: {e}")
                    _low_power_since.pop(sid, None)
                    continue

                if power_kw < LOW_POWER_THRESHOLD:
                    if sid not in _low_power_since:
                        _low_power_since[sid] = time.time()
                        print(f"[AutoStop] Sta.{sid}: {power_kw:.3f}kW < {LOW_POWER_THRESHOLD}kW — Timer START")
                    else:
                        elapsed = time.time() - _low_power_since[sid]
                        print(f"[AutoStop] Sta.{sid}: {elapsed:.0f}s/{LOW_POWER_DURATION}s @ {power_kw:.3f}kW")
                        if elapsed >= LOW_POWER_DURATION:
                            # ── SESSION BEENDEN ──
                            now_ms = int(time.time() * 1000)
                            # kWh: delta von Shelly-Zähler wenn vorhanden
                            start_kwh = sess.get("start_total_kwh")
                            if start_kwh and total_kwh > float(start_kwh):
                                kwh = round(total_kwh - float(start_kwh), 3)
                            else:
                                kwh = round(float(sess.get("kwh") or 0), 3)
                            tariff = float(sess.get("tariff") or st["tariff"])
                            chf = round(kwh * tariff, 2)
                            supa_patch("sessions", f"id=eq.{sess['id']}",
                                {"stopped_at": now_ms, "kwh": kwh, "chf": chf})
                            # Relay AUS
                            if st["ip_mini"]:
                                try:
                                    requests.get(f"http://{st['ip_mini']}/relay/0?turn=off", timeout=3)
                                except: pass
                            _low_power_since.pop(sid, None)
                            u = supa_get("cg_users", f"id=eq.{sess['user_id']}&select=name")
                            uname = u[0]["name"] if u else "?"
                            print(f"[AutoStop] ✅ Sta.{sid} STOP: {uname} — {kwh:.2f}kWh / {chf:.2f}CHF")
                else:
                    if sid in _low_power_since:
                        print(f"[AutoStop] Sta.{sid}: Leistung {power_kw:.3f}kW — Timer RESET")
                    _low_power_since.pop(sid, None)

        except Exception as e:
            print(f"[AutoStop] Fehler im Loop: {e}")
        time.sleep(15)

# Thread beim Start starten
_autostop_thread = threading.Thread(target=auto_stop_loop, daemon=True)
_autostop_thread.start()
print(f"[AutoStop] Thread gestartet — Schwelle: {LOW_POWER_THRESHOLD}kW / {LOW_POWER_DURATION}s")

# ── STATUS ──────────────────────────────────────────────────
@APP.route("/api/status")
def status():
    cf = ""
    try:
        with open("/opt/charge-goertz/tunnel_url.txt") as f:
            cf = f.read().strip()
    except: pass
    return jsonify({"status":"ok","version":"4.1","pi":True,"ts":int(time.time()*1000),"cf_url":cf})

# ── TUNNEL URL ───────────────────────────────────────────────
@APP.route("/api/tunnel")
def tunnel():
    try:
        import subprocess
        r = subprocess.run(["journalctl","-u","cloudflared-cg","--no-pager","--lines=50"],
            capture_output=True, text=True)
        import re
        urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", r.stdout)
        if urls:
            url = urls[-1]
            with open("/opt/charge-goertz/tunnel_url.txt","w") as f: f.write(url)
            return jsonify({"url":url,"active":True,"type":"quick"})
    except: pass
    try:
        with open("/opt/charge-goertz/tunnel_url.txt") as f:
            url = f.read().strip()
        return jsonify({"url":url,"active":bool(url),"type":"named" if "robcat" in url else "quick"})
    except:
        return jsonify({"url":None,"active":False})

# ── USERS API ────────────────────────────────────────────────
@APP.route("/api/users", methods=["GET"])
def get_users():
    users = supa_get("cg_users", "select=*&active=eq.true&order=id.asc")
    for u in users:
        u.pop("pin", None)
    return jsonify(users)

@APP.route("/api/users/<int:uid>", methods=["GET"])
def get_user(uid):
    users = supa_get("cg_users", f"select=*&id=eq.{uid}&active=eq.true")
    if not users: return jsonify({"error":"not found"}), 404
    u = users[0]; u.pop("pin", None)
    return jsonify(u)

@APP.route("/api/users/verify", methods=["POST"])
def verify_user():
    data = request.json or {}
    uid = data.get("user_id")
    pin = str(data.get("pin",""))
    if not uid or not pin:
        return jsonify({"ok":False,"error":"missing"}), 400
    users = supa_get("cg_users", f"select=id,name,emoji,role,stations,color,pin&id=eq.{uid}&active=eq.true")
    if not users: return jsonify({"ok":False,"error":"not found"}), 404
    u = users[0]
    if u.get("pin") == pin:
        u.pop("pin")
        return jsonify({"ok":True,"user":u})
    return jsonify({"ok":False,"error":"wrong pin"})

@APP.route("/api/users", methods=["POST"])
def create_user():
    data = request.json or {}
    required = ["name","pin","emoji"]
    if not all(k in data for k in required):
        return jsonify({"error":"name, pin, emoji required"}), 400
    user = {
        "name": data["name"], "emoji": data.get("emoji","👤"),
        "pin": str(data["pin"]), "role": data.get("role","user"),
        "stations": data.get("stations",[1]), "color": data.get("color","#00d4ff"),
        "plate": data.get("plate","—"), "active": True
    }
    result = supa_post("cg_users", user)
    if result:
        r = result[0] if isinstance(result,list) else result
        r.pop("pin",None)
        return jsonify(r), 201
    return jsonify({"error":"failed"}), 500

@APP.route("/api/users/<int:uid>", methods=["PUT"])
def update_user(uid):
    data = request.json or {}
    data.pop("id",None)
    ok = supa_patch("cg_users", f"id=eq.{uid}", data)
    return jsonify({"ok":ok})

@APP.route("/api/users/<int:uid>", methods=["DELETE"])
def delete_user(uid):
    ok = supa_patch("cg_users", f"id=eq.{uid}", {"active":False})
    return jsonify({"ok":ok})

# ── DEVICE REGISTRATION ───────────────────────────────────────
@APP.route("/api/device/register", methods=["POST"])
def register_device():
    data = request.json or {}
    device_id = data.get("device_id")
    user_id = data.get("user_id")
    device_name = data.get("device_name","Unbekannt")
    if not device_id or not user_id:
        return jsonify({"error":"device_id and user_id required"}), 400
    existing = supa_get("devices", f"device_id=eq.{device_id}")
    if existing:
        supa_patch("devices", f"device_id=eq.{device_id}",
            {"user_id":user_id,"device_name":device_name,"last_seen":"now()"})
    else:
        supa_post("devices", {"device_id":device_id,"user_id":user_id,"device_name":device_name})
    return jsonify({"ok":True,"device_id":device_id,"user_id":user_id})

@APP.route("/api/device/<device_id>", methods=["GET"])
def get_device(device_id):
    devices = supa_get("devices", f"device_id=eq.{device_id}&select=user_id,device_name")
    if not devices: return jsonify({"user":None})
    uid = devices[0]["user_id"]
    users = supa_get("cg_users", f"id=eq.{uid}&active=eq.true&select=id,name,emoji,role,stations,color")
    if not users: return jsonify({"user":None})
    return jsonify({"user":users[0],"device_name":devices[0]["device_name"]})

@APP.route("/api/device/<device_id>", methods=["DELETE"])
def unregister_device(device_id):
    ok = supa_delete("devices", f"device_id=eq.{device_id}")
    return jsonify({"ok":ok})

# ── ENERGY ───────────────────────────────────────────────────
@APP.route("/api/energy/<int:sid>")
def energy(sid):
    ip = STATIONS.get(sid,{}).get("ip_3em","")
    if not ip:
        return jsonify({"demo":True,"power_w":0,"power_kw":0,"voltage_v":230,"current_a":0,"total_kwh":0,"phases":[]})
    try:
        r = requests.get(f"http://{ip}/status", timeout=4).json()
        em = r.get("emeters",[])
        phases = [{"phase":i+1,"power_w":round(e.get("power",0),1),
            "voltage_v":round(e.get("voltage",0),1),"current_a":round(e.get("current",0),3),
            "total_kwh":round(e.get("total",0)/1000,3),"active":abs(e.get("power",0))>50}
            for i,e in enumerate(em)]
        total_w = r.get("total_power", sum(e.get("power",0) for e in em))
        total_kwh = sum(e.get("total",0) for e in em)/1000
        return jsonify({"demo":False,"power_w":round(total_w,1),"power_kw":round(total_w/1000,3),
            "voltage_v":round(em[0].get("voltage",230),1) if em else 230,
            "current_a":round(sum(e.get("current",0) for e in em),2),
            "total_kwh":round(total_kwh,3),"phases":phases})
    except Exception as e:
        return jsonify({"demo":True,"error":str(e),"power_w":0,"power_kw":0,
            "voltage_v":230,"current_a":0,"total_kwh":0,"phases":[]})

# ── RELAY ────────────────────────────────────────────────────
@APP.route("/api/relay/<int:sid>/<action>")
def relay(sid, action):
    if action not in ("on","off"): return jsonify({"error":"invalid"}),400
    ip = STATIONS.get(sid,{}).get("ip_mini","")
    ok = False
    if ip:
        try:
            requests.get(f"http://{ip}/relay/0?turn={action}", timeout=3)
            ok = True
        except: pass
    return jsonify({"action":action,"success":ok,"demo":not ok})

# ── SHELLY RESET ─────────────────────────────────────────────
@APP.route("/api/shelly/reset/<int:sid>", methods=["POST"])
def reset_shelly(sid):
    ip = STATIONS.get(sid,{}).get("ip_3em","")
    if not ip: return jsonify({"error":"no ip"}),400
    try:
        r = requests.get(f"http://{ip}/status", timeout=4).json()
        em = r.get("emeters",[])
        total_kwh = sum(e.get("total",0) for e in em)/1000
        reset_ok = []
        for i in range(3):
            try:
                resp = requests.post(f"http://{ip}/emeter/{i}/reset_data", timeout=3)
                reset_ok.append(resp.status_code==200)
            except: reset_ok.append(False)
        supa_post("energy_log",{"station_id":sid,"ts":int(time.time()*1000),
            "power_w":0,"total_kwh":round(total_kwh,3),"note":f"RESET (Stand: {total_kwh:.3f} kWh)"})
        return jsonify({"ok":True,"phases_reset":reset_ok,
            "kwh_before_reset":round(total_kwh,3),
            "message":f"Zähler zurückgesetzt (vorher: {total_kwh:.2f} kWh)"})
    except Exception as e:
        return jsonify({"error":str(e)}),500

# ── STATIONS ─────────────────────────────────────────────────
@APP.route("/api/stations")
def stations():
    result = []
    for sid, st in STATIONS.items():
        relay_on = False
        if st["ip_mini"]:
            try:
                r = requests.get(f"http://{st['ip_mini']}/relay/0", timeout=2).json()
                relay_on = r.get("ison",False)
            except: pass
        result.append({"id":sid,"name":st["name"],"ip_3em":st["ip_3em"],
            "ip_mini":st["ip_mini"],"tariff":st["tariff"],"relay_on":relay_on})
    return jsonify(result)

# ── STATIC ───────────────────────────────────────────────────
@APP.route("/")
def index(): return send_from_directory("/opt/charge-goertz/web","index.html")
@APP.route("/<path:f>")
def static_f(f): return send_from_directory("/opt/charge-goertz/web",f)

if __name__=="__main__":
    APP.run(host="0.0.0.0",port=5000,debug=False)
