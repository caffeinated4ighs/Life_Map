-- ============================================================
-- 003_rls.sql
-- Life System — Row Level Security
-- Single-user system: authenticated role gets full CRUD
-- Idempotent: DROP POLICY IF EXISTS before re-creating
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- STATS
-- ────────────────────────────────────────────────────────────
ALTER TABLE stats ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_stats_authenticated ON stats;
CREATE POLICY policy_stats_authenticated ON stats
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- SKILLS
-- ────────────────────────────────────────────────────────────
ALTER TABLE skills ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_skills_authenticated ON skills;
CREATE POLICY policy_skills_authenticated ON skills
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- ARCS
-- ────────────────────────────────────────────────────────────
ALTER TABLE arcs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_arcs_authenticated ON arcs;
CREATE POLICY policy_arcs_authenticated ON arcs
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- EFFECTS
-- ────────────────────────────────────────────────────────────
ALTER TABLE effects ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_effects_authenticated ON effects;
CREATE POLICY policy_effects_authenticated ON effects
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- ANCHORS
-- ────────────────────────────────────────────────────────────
ALTER TABLE anchors ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_anchors_authenticated ON anchors;
CREATE POLICY policy_anchors_authenticated ON anchors
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- TASKS
-- ────────────────────────────────────────────────────────────
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_tasks_authenticated ON tasks;
CREATE POLICY policy_tasks_authenticated ON tasks
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- TASK_SKILL_LINKS
-- ────────────────────────────────────────────────────────────
ALTER TABLE task_skill_links ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_task_skill_links_authenticated ON task_skill_links;
CREATE POLICY policy_task_skill_links_authenticated ON task_skill_links
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- ARC_TASKS
-- ────────────────────────────────────────────────────────────
ALTER TABLE arc_tasks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_arc_tasks_authenticated ON arc_tasks;
CREATE POLICY policy_arc_tasks_authenticated ON arc_tasks
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- TASK_STATS
-- ────────────────────────────────────────────────────────────
ALTER TABLE task_stats ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_task_stats_authenticated ON task_stats;
CREATE POLICY policy_task_stats_authenticated ON task_stats
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- ARC_SKILLS
-- ────────────────────────────────────────────────────────────
ALTER TABLE arc_skills ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_arc_skills_authenticated ON arc_skills;
CREATE POLICY policy_arc_skills_authenticated ON arc_skills
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- EFFECT_STATS
-- ────────────────────────────────────────────────────────────
ALTER TABLE effect_stats ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_effect_stats_authenticated ON effect_stats;
CREATE POLICY policy_effect_stats_authenticated ON effect_stats
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- EFFECT_ARCS
-- ────────────────────────────────────────────────────────────
ALTER TABLE effect_arcs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_effect_arcs_authenticated ON effect_arcs;
CREATE POLICY policy_effect_arcs_authenticated ON effect_arcs
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- EVENTS
-- ────────────────────────────────────────────────────────────
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_events_authenticated ON events;
CREATE POLICY policy_events_authenticated ON events
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- PLAYER_STATE
-- ────────────────────────────────────────────────────────────
ALTER TABLE player_state ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_player_state_authenticated ON player_state;
CREATE POLICY policy_player_state_authenticated ON player_state
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- DAY_SNAPSHOTS
-- ────────────────────────────────────────────────────────────
ALTER TABLE day_snapshots ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_day_snapshots_authenticated ON day_snapshots;
CREATE POLICY policy_day_snapshots_authenticated ON day_snapshots
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- SNAPSHOT_ANCHORS
-- ────────────────────────────────────────────────────────────
ALTER TABLE snapshot_anchors ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_snapshot_anchors_authenticated ON snapshot_anchors;
CREATE POLICY policy_snapshot_anchors_authenticated ON snapshot_anchors
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ────────────────────────────────────────────────────────────
-- STREAK_LOG
-- ────────────────────────────────────────────────────────────
ALTER TABLE streak_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS policy_streak_log_authenticated ON streak_log;
CREATE POLICY policy_streak_log_authenticated ON streak_log
    FOR ALL TO authenticated USING (true) WITH CHECK (true);
