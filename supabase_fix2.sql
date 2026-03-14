-- ═══════════════════════════════════════════
-- ChargeGörtz: NEUE cg_users + devices Tabelle
-- (users = Supabase Auth-System → nicht anfassen!)
-- ═══════════════════════════════════════════

-- ChargeGörtz Benutzer (eigene Tabelle)
CREATE TABLE IF NOT EXISTS cg_users (
  id          SERIAL PRIMARY KEY,
  name        TEXT NOT NULL,
  emoji       TEXT DEFAULT '👤',
  pin         TEXT NOT NULL,
  role        TEXT DEFAULT 'user',
  stations    JSONB DEFAULT '[1]',
  color       TEXT DEFAULT '#00d4ff',
  plate       TEXT DEFAULT '—',
  active      BOOLEAN DEFAULT true,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Geräte für Auto-Login
CREATE TABLE IF NOT EXISTS devices (
  id          SERIAL PRIMARY KEY,
  user_id     INTEGER REFERENCES cg_users(id) ON DELETE CASCADE,
  device_id   TEXT NOT NULL UNIQUE,
  device_name TEXT DEFAULT 'Unbekannt',
  last_seen   TIMESTAMPTZ DEFAULT NOW(),
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- RLS deaktivieren
ALTER TABLE cg_users DISABLE ROW LEVEL SECURITY;
ALTER TABLE devices  DISABLE ROW LEVEL SECURITY;

-- Benutzer einfügen
INSERT INTO cg_users (id, name, emoji, pin, role, stations, color, plate)
VALUES
  (1, 'Robert Görtz', '⚡', '2204', 'admin', '[1,2]', '#00d4ff', 'ZH 100 RG'),
  (2, 'Cintia Görtz',  '🌿', '1803', 'admin', '[1,2]', '#00e676', 'ZH 200 CG'),
  (3, 'Carolina',      '🌸', '1111', 'user',  '[1]',   '#f06292', '—'),
  (4, 'Sabrina',       '⭐', '2222', 'user',  '[1]',   '#ffd740', '—'),
  (5, 'Fam. Hitzler',  '🏠', '3333', 'user',  '[2]',   '#ff7c2a', '—')
ON CONFLICT (id) DO NOTHING;

SELECT setval('cg_users_id_seq', 10);

-- Prüfen
SELECT id, name, emoji, role FROM cg_users ORDER BY id;
