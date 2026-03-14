#!/usr/bin/env python3
"""
ChargeGörtz Push Daemon — läuft im Hintergrund auf dem Pi
Prüft alle 30s ob jemand lädt ohne aktive Session
Falls ja → Push an Admins
"""
import time, requests, json, os, logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger('push')

SHELLY_3EM_IP = "192.168.3.223"
FLASK_BASE    = "http://127.0.0.1:5000"
SUPA_URL      = "https://vloululxbazfcvlhmtzr.supabase.co"
SUPA_KEY      = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZsb3VsdWx4YmF6ZmN2bGhtdHpyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMxNDEyOTcsImV4cCI6MjA4ODcxNzI5N30.pUrwkI2g2DpA7q7o0cSEWzXGeUiJxO74TdLj7iEd3N8"
HDR = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"}

CHECK_INTERVAL  = 30   # Sekunden
POWER_THRESHOLD = 200  # Watt — unter diesem Wert = kein Laden
alert_sent = False
last_kwh_save = 0

def get_shelly_power():
    try:
        r = requests.get(f"http://{SHELLY_3EM_IP}/status", timeout=4).json()
        return r.get("total_power", 0), r
    except:
        return 0, {}

def has_active_session():
    try:
        r = requests.get(f"{SUPA_URL}/rest/v1/sessions?select=id&stopped_at=is.null&station_id=eq.1&limit=1",
                        headers=HDR, timeout=5)
        return len(r.json()) > 0
    except:
        return True  # Im Zweifel: keine Warnung

def save_energy_log(total_w, shelly_data):
    em = shelly_data.get("emeters", [])
    total_kwh = sum(e.get("total",0) for e in em) / 1000
    payload = {
        "station_id": 1,
        "ts": int(time.time() * 1000),
        "power_w": round(total_w, 1),
        "total_kwh": round(total_kwh, 3),
        "phase1_w": round(em[0].get("power",0),1) if len(em)>0 else 0,
        "phase2_w": round(em[1].get("power",0),1) if len(em)>1 else 0,
        "phase3_w": round(em[2].get("power",0),1) if len(em)>2 else 0,
    }
    try:
        requests.post(f"{SUPA_URL}/rest/v1/energy_log",
            headers={**HDR, "Content-Type":"application/json", "Prefer":"return=minimal"},
            json=payload, timeout=5)
    except Exception as e:
        log.warning(f"energy_log save failed: {e}")

def send_push_notification(title, body):
    """Lokale Benachrichtigung via Supabase → App"""
    try:
        requests.post(f"{SUPA_URL}/rest/v1/push_events",
            headers={**HDR, "Content-Type":"application/json", "Prefer":"return=minimal"},
            json={"title": title, "body": body, "ts": int(time.time()*1000), "read": False},
            timeout=5)
        log.info(f"Push event: {title} — {body}")
    except Exception as e:
        log.warning(f"Push failed: {e}")

def main():
    global alert_sent, last_kwh_save
    log.info("ChargeGörtz Push Daemon gestartet")
    while True:
        try:
            power_w, shelly_data = get_shelly_power()
            now = time.time()

            # Shelly kWh alle 5 Min in Supabase speichern
            if now - last_kwh_save > 300:
                save_energy_log(power_w, shelly_data)
                last_kwh_save = now

            if power_w > POWER_THRESHOLD:
                active = has_active_session()
                if not active and not alert_sent:
                    log.warning(f"UNBEKANNTES LADEN: {power_w:.0f}W — keine aktive Session!")
                    send_push_notification(
                        "⚠ ChargeGörtz — Unbekanntes Laden",
                        f"Es wird ohne Session geladen: {power_w/1000:.2f} kW\n{datetime.now().strftime('%H:%M:%S')}"
                    )
                    alert_sent = True
                elif active:
                    alert_sent = False
            else:
                alert_sent = False

        except Exception as e:
            log.error(f"Main loop error: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
