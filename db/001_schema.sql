-- ============================================================
-- 001_schema.sql
-- Life System — full schema migration
-- Idempotent: safe to run multiple times
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. STATS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stats (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    stat         text        NOT NULL UNIQUE,
    current_value numeric    NOT NULL DEFAULT 0,
    last_updated  date,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- ────────────────────────────────────────────────────────────
-- 2. SKILLS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skills (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    skill             text        NOT NULL,
    current_level     integer     NOT NULL DEFAULT 1,
    xp_accumulated    integer     NOT NULL DEFAULT 0,
    xp_to_next_level  integer     NOT NULL,
    decay_rate        text,
    last_active       date,
    in_decay          boolean     NOT NULL DEFAULT false,
    primary_stat_id   uuid        NOT NULL,
    secondary_stat_id uuid,
    created_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_skills_decay_rate
        CHECK (decay_rate IN ('Slow', 'Medium', 'Fast')),

    CONSTRAINT fk_skills_stats_primary
        FOREIGN KEY (primary_stat_id)   REFERENCES stats(id),

    CONSTRAINT fk_skills_stats_secondary
        FOREIGN KEY (secondary_stat_id) REFERENCES stats(id)
);

-- ────────────────────────────────────────────────────────────
-- 3. ARCS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS arcs (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    arc        text        NOT NULL,
    status     text        NOT NULL DEFAULT 'Active',
    weight     text,
    start_date date,
    end_date   date,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_arcs_status
        CHECK (status IN ('Active', 'Paused', 'Done')),

    CONSTRAINT chk_arcs_weight
        CHECK (weight IN ('Background', 'Normal', 'Focused', 'Critical'))
);

-- ────────────────────────────────────────────────────────────
-- 4. EFFECTS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS effects (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    effect                  text        NOT NULL,
    type                    text,
    intensity               integer,
    suppresses_arc_pressure boolean     NOT NULL DEFAULT false,
    duration_days           integer     NOT NULL,
    created_on              date        NOT NULL DEFAULT CURRENT_DATE,
    expires_on              date        NOT NULL,
    active                  boolean     NOT NULL DEFAULT true,
    stat_offset             integer     NOT NULL DEFAULT 0,
    created_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_effects_type
        CHECK (type IN ('Buff', 'Debuff')),

    CONSTRAINT chk_effects_intensity
        CHECK (intensity BETWEEN 1 AND 10)
);

-- ────────────────────────────────────────────────────────────
-- 5. ANCHORS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anchors (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    anchor            text        NOT NULL,
    type              text,
    date              date        NOT NULL,
    time              text,
    priority_pressure text,
    created_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_anchors_type
        CHECK (type IN ('Class', 'Appointment', 'Commitment', 'Other')),

    CONSTRAINT chk_anchors_priority_pressure
        CHECK (priority_pressure IN ('None', 'Elevates Tasks', 'Locks Day'))
);

-- ────────────────────────────────────────────────────────────
-- 6. TASKS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    task                text        NOT NULL,
    type                text,
    status              text        NOT NULL DEFAULT 'Not started',
    priority            text,
    category            text,
    date                date        NOT NULL,
    energy_cost         text,
    late_rule           text,
    late_rule_behavior  text        NOT NULL DEFAULT 'Penalty',
    mandatory           boolean     NOT NULL DEFAULT false,
    blocked             boolean     NOT NULL DEFAULT false,
    deferred            boolean     NOT NULL DEFAULT false,
    xp                  integer     NOT NULL DEFAULT 0,
    gold                integer     NOT NULL DEFAULT 0,
    resolved_xp         integer,
    resolved_gold       integer,
    streak_xp           integer,
    mh_impact           integer     NOT NULL DEFAULT 0,
    anchor_id           uuid,
    crossover_level     text        NOT NULL DEFAULT 'Direct',
    time_block          text,
    class_day_fit       text,
    reminder_needed     boolean     NOT NULL DEFAULT false,
    reminder_lead       text,
    recurring_rule      text,
    impact_notes        text,
    anchor_override     boolean     NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_tasks_type
        CHECK (type IN ('Daily', 'Weekly', 'Recurring', 'Mandatory', 'Optional', 'Bonus')),

    CONSTRAINT chk_tasks_status
        CHECK (status IN ('Not started', 'In progress', 'Done')),

    CONSTRAINT chk_tasks_priority
        CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),

    CONSTRAINT chk_tasks_category
        CHECK (category IN ('Health', 'Study', 'Work', 'Social', 'Maintenance', 'Hobby')),

    CONSTRAINT chk_tasks_energy_cost
        CHECK (energy_cost IN ('Low', 'Medium', 'High', 'Very High')),

    CONSTRAINT chk_tasks_late_rule
        CHECK (late_rule IN ('None', 'Soft', 'Medium', 'Hard')),

    CONSTRAINT chk_tasks_late_rule_behavior
        CHECK (late_rule_behavior IN ('Penalty', 'Incentive', 'Neutral')),

    CONSTRAINT chk_tasks_crossover_level
        CHECK (crossover_level IN ('Indirect', 'Partial', 'Direct')),

    CONSTRAINT chk_tasks_time_block
        CHECK (time_block IN ('Morning', 'Afternoon', 'Evening', 'Night', 'Flexible')),

    CONSTRAINT chk_tasks_class_day_fit
        CHECK (class_day_fit IN ('Yes', 'Light Only', 'No')),

    CONSTRAINT chk_tasks_reminder_lead
        CHECK (reminder_lead IN ('15 min', '30 min', '1 hour', '2 hours')),

    CONSTRAINT fk_tasks_anchors
        FOREIGN KEY (anchor_id) REFERENCES anchors(id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_date        ON tasks (date);
CREATE INDEX IF NOT EXISTS idx_tasks_status      ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_date_status ON tasks (date, status);

-- ────────────────────────────────────────────────────────────
-- 7. TASK_SKILL_LINKS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS task_skill_links (
    id              uuid NOT NULL DEFAULT gen_random_uuid(),
    task_id         uuid NOT NULL,
    skill_id        uuid NOT NULL,
    crossover_level text NOT NULL,

    CONSTRAINT task_skill_links_pkey
        PRIMARY KEY (id),

    CONSTRAINT uq_task_skill_links_task_skill
        UNIQUE (task_id, skill_id),

    CONSTRAINT chk_task_skill_links_crossover_level
        CHECK (crossover_level IN ('Indirect', 'Partial', 'Direct')),

    CONSTRAINT fk_task_skill_links_tasks
        FOREIGN KEY (task_id)  REFERENCES tasks(id)  ON DELETE CASCADE,

    CONSTRAINT fk_task_skill_links_skills
        FOREIGN KEY (skill_id) REFERENCES skills(id)
);

-- ────────────────────────────────────────────────────────────
-- 8. ARC_TASKS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS arc_tasks (
    arc_id  uuid NOT NULL,
    task_id uuid NOT NULL,

    CONSTRAINT arc_tasks_pkey
        PRIMARY KEY (arc_id, task_id),

    CONSTRAINT fk_arc_tasks_arcs
        FOREIGN KEY (arc_id)  REFERENCES arcs(id)  ON DELETE CASCADE,

    CONSTRAINT fk_arc_tasks_tasks
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- ────────────────────────────────────────────────────────────
-- 9. TASK_STATS
-- Junction: direct stat deltas applied on task completion
-- stat_delta is the flat value added to stats.current_value
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS task_stats (
    task_id    uuid    NOT NULL,
    stat_id    uuid    NOT NULL,
    stat_delta integer NOT NULL DEFAULT 0,

    CONSTRAINT task_stats_pkey
        PRIMARY KEY (task_id, stat_id),

    CONSTRAINT fk_task_stats_tasks
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,

    CONSTRAINT fk_task_stats_stats
        FOREIGN KEY (stat_id) REFERENCES stats(id)
);

-- ────────────────────────────────────────────────────────────
-- 10. ARC_SKILLS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS arc_skills (
    arc_id   uuid NOT NULL,
    skill_id uuid NOT NULL,

    CONSTRAINT arc_skills_pkey
        PRIMARY KEY (arc_id, skill_id),

    CONSTRAINT fk_arc_skills_arcs
        FOREIGN KEY (arc_id)   REFERENCES arcs(id)   ON DELETE CASCADE,

    CONSTRAINT fk_arc_skills_skills
        FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
);

-- ────────────────────────────────────────────────────────────
-- 11. EFFECT_STATS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS effect_stats (
    effect_id uuid NOT NULL,
    stat_id   uuid NOT NULL,

    CONSTRAINT effect_stats_pkey
        PRIMARY KEY (effect_id, stat_id),

    CONSTRAINT fk_effect_stats_effects
        FOREIGN KEY (effect_id) REFERENCES effects(id) ON DELETE CASCADE,

    CONSTRAINT fk_effect_stats_stats
        FOREIGN KEY (stat_id)   REFERENCES stats(id)   ON DELETE CASCADE
);

-- ────────────────────────────────────────────────────────────
-- 12. EFFECT_ARCS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS effect_arcs (
    effect_id uuid NOT NULL,
    arc_id    uuid NOT NULL,

    CONSTRAINT effect_arcs_pkey
        PRIMARY KEY (effect_id, arc_id),

    CONSTRAINT fk_effect_arcs_effects
        FOREIGN KEY (effect_id) REFERENCES effects(id) ON DELETE CASCADE,

    CONSTRAINT fk_effect_arcs_arcs
        FOREIGN KEY (arc_id)    REFERENCES arcs(id)    ON DELETE CASCADE
);

-- ────────────────────────────────────────────────────────────
-- 13. EVENTS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS events (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    date             date        NOT NULL,
    event_type       text        NOT NULL,
    name             text,
    quantity         numeric,
    duration_minutes integer,
    gold_delta       integer     NOT NULL DEFAULT 0,
    mh_delta         integer     NOT NULL DEFAULT 0,
    notes            text,
    created_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_events_event_type
        CHECK (event_type IN ('steps', 'substance', 'leisure', 'day_off', 'cheat_day', 'mh_manual'))
);

CREATE INDEX IF NOT EXISTS idx_events_date      ON events (date);
CREATE INDEX IF NOT EXISTS idx_events_type_date ON events (event_type, date);

-- ────────────────────────────────────────────────────────────
-- 14. PLAYER_STATE  (singleton)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS player_state (
    id            integer     PRIMARY KEY,
    mh_score      integer     NOT NULL,
    mh_mode       text        NOT NULL,
    gold_balance  integer     NOT NULL DEFAULT 0,
    streak_count  integer     NOT NULL DEFAULT 0,
    total_xp      integer     NOT NULL DEFAULT 0,
    last_updated  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_player_state_id
        CHECK (id = 1),

    CONSTRAINT chk_player_state_mh_score
        CHECK (mh_score BETWEEN 0 AND 100),

    CONSTRAINT chk_player_state_mh_mode
        CHECK (mh_mode IN ('Normal', 'Reduced', 'Minimum Viable', 'Recovery Only'))
);

-- ────────────────────────────────────────────────────────────
-- 15. DAY_SNAPSHOTS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS day_snapshots (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    date            date        NOT NULL UNIQUE,
    mh_score_open   integer,
    mh_score_close  integer,
    mh_mode         text,
    gold_open       integer,
    gold_close      integer,
    xp_earned       integer     NOT NULL DEFAULT 0,
    steps           integer     NOT NULL DEFAULT 0,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- ────────────────────────────────────────────────────────────
-- 16. SNAPSHOT_ANCHORS
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS snapshot_anchors (
    snapshot_id uuid NOT NULL,
    anchor_id   uuid NOT NULL,

    CONSTRAINT snapshot_anchors_pkey
        PRIMARY KEY (snapshot_id, anchor_id),

    CONSTRAINT fk_snapshot_anchors_day_snapshots
        FOREIGN KEY (snapshot_id) REFERENCES day_snapshots(id) ON DELETE CASCADE,

    CONSTRAINT fk_snapshot_anchors_anchors
        FOREIGN KEY (anchor_id)   REFERENCES anchors(id)       ON DELETE CASCADE
);

-- ────────────────────────────────────────────────────────────
-- 17. STREAK_LOG
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS streak_log (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    date           date        NOT NULL UNIQUE,
    mandatory_met  boolean     NOT NULL,
    streak_count   integer     NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);
