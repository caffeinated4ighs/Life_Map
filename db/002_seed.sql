-- ============================================================
-- 002_seed.sql
-- Life System — initial seed data
-- Idempotent: uses INSERT ... ON CONFLICT DO NOTHING
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- STATS — nine core stats, all starting at 0
-- ────────────────────────────────────────────────────────────
INSERT INTO stats (stat, current_value) VALUES
    ('Intellect',  0),
    ('Dexterity',  0),
    ('Endurance',  0),
    ('Strength',   0),
    ('Coding',     0),
    ('Admin',      0),
    ('Charisma',   0),
    ('Social',     0),
    ('Discipline', 0)
ON CONFLICT (stat) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- PLAYER_STATE — singleton row (id = 1)
-- ────────────────────────────────────────────────────────────
INSERT INTO player_state (id, mh_score, mh_mode, gold_balance, streak_count, total_xp)
VALUES (1, 75, 'Reduced', 50, 0, 0)
ON CONFLICT (id) DO NOTHING;
