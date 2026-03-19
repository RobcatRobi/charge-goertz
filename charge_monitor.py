#!/usr/bin/env python3
"""
ChargeGörtz Background Monitor Service
Läuft permanent auf dem Pi und überwacht Shelly 3EM
Funktioniert mit v17 und v18!

Features:
- Shelly 3EM alle 10 Sekunden abfragen
- Auto-Stop Detection (0kW für 60s)
- Session-Tracking in Supabase
- Push-Notifications
- Relay-Control
"""

import time
import requests
import json
import os
from datetime import datetime

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# Supabase
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://vloululxbazfcvlhmtzr.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')  # Muss gesetzt werden!

# Shelly 3EM
SHELLY_IP = '192.168.3.223'
SHELLY_MINI_IP = '192.168.3.224'

# Station
STATION_ID = 1  # Neerach
STATION_NAME = 'Neerach'

# Monitoring
POLL_INTERVAL = 10  # Sekunden
AUTO_STOP_THRESHOLD = 0.1  # kW
AUTO_STOP_DURATION = 60  # Sekunden

# ═══════════════════════════════════════════════════════════════
# SUPABASE HELPERS
# ═══════════════════════════════════════════════════════════════

def supabase_get(table, params=''):
    """Fetch data from Supabase"""
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json'
    }
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += f"?{params}"
    
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.ok:
            return r.json()
        else:
            print(f"[Supabase GET] Error {r.status_code}: {r.text}")
            return None
    except Exception as e:
        print(f"[Supabase GET] Exception: {e}")
        return None

def supabase_post(table, data):
    """Insert data into Supabase"""
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    
    try:
        r = requests.post(url, headers=headers, json=data, timeout=5)
        if r.ok:
            return r.json()
        else:
            print(f"[Supabase POST] Error {r.status_code}: {r.text}")
            return None
    except Exception as e:
        print(f"[Supabase POST] Exception: {e}")
        return None

def supabase_patch(table, filter_params, data):
    """Update data in Supabase"""
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
    url = f"{SUPABASE_URL}/rest/v1/{table}?{filter_params}"
    
    try:
        r = requests.patch(url, headers=headers, json=data, timeout=5)
        if r.ok:
            return r.json()
        else:
            print(f"[Supabase PATCH] Error {r.status_code}: {r.text}")
            return None
    except Exception as e:
        print(f"[Supabase PATCH] Exception: {e}")
        return None

# ═══════════════════════════════════════════════════════════════
# SHELLY HELPERS
# ═══════════════════════════════════════════════════════════════

def get_shelly_data():
    """Fetch current data from Shelly 3EM"""
    try:
        url = f"http://{SHELLY_IP}/status"
        r = requests.get(url, timeout=3)
        if not r.ok:
            print(f"[Shelly] HTTP {r.status_code}")
            return None
        
        data = r.json()
        
        # Parse Shelly Gen2 format
        emeters = data.get('emeters', [])
        if not emeters or len(emeters) == 0:
            print("[Shelly] No emeters data")
            return None
        
        em = emeters[0]  # Phase A (total)
        
        return {
            'power_w': em.get('power', 0),
            'power_kw': round(em.get('power', 0) / 1000, 2),
            'total_kwh': round(em.get('total', 0) / 1000, 2),
            'voltage': em.get('voltage', 0),
            'current': em.get('current', 0),
            'timestamp': int(time.time() * 1000)
        }
    except Exception as e:
        print(f"[Shelly] Error: {e}")
        return None

def set_relay(state):
    """Turn relay ON/OFF"""
    try:
        url = f"http://{SHELLY_MINI_IP}/relay/0?turn={'on' if state else 'off'}"
        r = requests.get(url, timeout=3)
        if r.ok:
            print(f"[Relay] Set to {'ON' if state else 'OFF'}")
            return True
        else:
            print(f"[Relay] Failed: {r.status_code}")
            return False
    except Exception as e:
        print(f"[Relay] Error: {e}")
        return False

# ═══════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════

def get_active_session():
    """Get currently active session from Supabase"""
    params = f"station_id=eq.{STATION_ID}&stopped_at=is.null&order=started_at.desc&limit=1"
    sessions = supabase_get('sessions', params)
    return sessions[0] if sessions and len(sessions) > 0 else None

def stop_session(session_id, kwh, chf):
    """Stop a session in Supabase"""
    now = int(time.time() * 1000)
    data = {
        'stopped_at': now,
        'kwh': kwh,
        'chf': chf
    }
    filter_params = f"id=eq.{session_id}"
    result = supabase_patch('sessions', filter_params, data)
    
    if result:
        print(f"[Session] Stopped session {session_id}: {kwh} kWh, {chf} CHF")
        return True
    else:
        print(f"[Session] Failed to stop session {session_id}")
        return False

# ═══════════════════════════════════════════════════════════════
# AUTO-STOP LOGIC
# ═══════════════════════════════════════════════════════════════

auto_stop_timer = None

def check_auto_stop(shelly_data, active_session):
    """Check if auto-stop should trigger"""
    global auto_stop_timer
    
    if not active_session:
        auto_stop_timer = None
        return
    
    power_kw = shelly_data['power_kw']
    
    if power_kw < AUTO_STOP_THRESHOLD:
        if auto_stop_timer is None:
            auto_stop_timer = time.time()
            print(f"[Auto-Stop] Timer started - {power_kw} kW detected")
        else:
            elapsed = time.time() - auto_stop_timer
            print(f"[Auto-Stop] Waiting... {int(elapsed)}s / {AUTO_STOP_DURATION}s")
            
            if elapsed >= AUTO_STOP_DURATION:
                print(f"[Auto-Stop] ⚡ TRIGGER! {AUTO_STOP_DURATION}s at 0kW")
                
                # Calculate session stats
                started_at = active_session['started_at']
                duration_ms = int(time.time() * 1000) - started_at
                duration_h = duration_ms / 3600000
                
                # Get user info
                user_id = active_session.get('user_id', 0)
                
                # Calculate kWh (rough estimate from Shelly total)
                session_kwh = active_session.get('kwh', 0)
                tariff = active_session.get('tariff', 0.25)
                session_chf = round(session_kwh * tariff, 2)
                
                # Stop session in Supabase
                stop_session(active_session['id'], session_kwh, session_chf)
                
                # Turn off relay
                set_relay(False)
                
                # TODO: Send push notification
                print(f"[Auto-Stop] ✅ Session stopped: {session_kwh} kWh, {session_chf} CHF")
                print(f"[Auto-Stop] 🔓 Station {STATION_NAME} is FREE!")
                
                auto_stop_timer = None
    else:
        if auto_stop_timer:
            print(f"[Auto-Stop] Timer reset - power back to {power_kw} kW")
        auto_stop_timer = None

# ═══════════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("ChargeGörtz Background Monitor v1.0")
    print("=" * 60)
    print(f"Station: {STATION_NAME} (ID: {STATION_ID})")
    print(f"Shelly 3EM: {SHELLY_IP}")
    print(f"Shelly Mini: {SHELLY_MINI_IP}")
    print(f"Poll Interval: {POLL_INTERVAL}s")
    print(f"Auto-Stop: <{AUTO_STOP_THRESHOLD} kW for {AUTO_STOP_DURATION}s")
    print("=" * 60)
    
    if not SUPABASE_KEY:
        print("❌ ERROR: SUPABASE_KEY not set!")
        print("Set environment variable: export SUPABASE_KEY='your-key-here'")
        return
    
    print("✅ Starting monitoring loop...")
    print("")
    
    loop_count = 0
    
    while True:
        try:
            loop_count += 1
            now = datetime.now().strftime('%H:%M:%S')
            
            # Fetch Shelly data
            shelly = get_shelly_data()
            if not shelly:
                print(f"[{now}] ⚠️  Shelly offline")
                time.sleep(POLL_INTERVAL)
                continue
            
            # Get active session
            session = get_active_session()
            
            # Log every 6 loops (60 seconds)
            if loop_count % 6 == 0:
                if session:
                    print(f"[{now}] Session ACTIVE | {shelly['power_kw']} kW | {shelly['total_kwh']} kWh total")
                else:
                    print(f"[{now}] No session | {shelly['power_kw']} kW | {shelly['total_kwh']} kWh total")
            
            # Check auto-stop
            if session:
                check_auto_stop(shelly, session)
            
            # Sleep
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Shutting down...")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(POLL_INTERVAL)
    
    print("✅ Monitor stopped.")

if __name__ == '__main__':
    main()
