"""
logic.py — Pure computation functions. No database access.

Every formula and lookup table from 00_SHARED_CONTEXT.md lives here.
A bug here cascades everywhere — keep fully tested.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# MH helpers
# ---------------------------------------------------------------------------

def derive_mh_mode(mh_score: int) -> str:
    """Return MH mode string for a given score."""
    if mh_score >= 80:
        return "Normal"
    if mh_score >= 60:
        return "Reduced"
    if mh_score >= 40:
        return "Minimum Viable"
    return "Recovery Only"


def clamp_mh(mh_score: int) -> int:
    """Clamp MH score to the legal 0–100 range."""
    return max(0, min(100, mh_score))


# ---------------------------------------------------------------------------
# Arc modifier
# ---------------------------------------------------------------------------

_ARC_WEIGHT_MODIFIERS: dict[str, float] = {
    "Background": 0.80,
    "Normal":     1.00,
    "Focused":    1.25,
    "Critical":   1.50,
}

_ARC_WEIGHT_ORDER = ["Background", "Normal", "Focused", "Critical"]


def get_arc_modifier(arc_weights: list[str]) -> float:
    """
    Resolve a single arc modifier from a list of arc weight strings.

    Rule: take the highest weight modifier; add at most +0.1 if a second
    distinct arc weight is present. Never fully stack.
    Returns 1.00 (Normal baseline) when the list is empty.
    """
    if not arc_weights:
        return 1.00

    # Sort weights by tier descending so [0] is the highest
    sorted_weights = sorted(
        arc_weights,
        key=lambda w: _ARC_WEIGHT_ORDER.index(w) if w in _ARC_WEIGHT_ORDER else -1,
        reverse=True,
    )

    primary = _ARC_WEIGHT_MODIFIERS.get(sorted_weights[0], 1.00)

    # Secondary bonus only applies when a second (different) arc is present
    if len(sorted_weights) >= 2 and sorted_weights[1] != sorted_weights[0]:
        return primary + 0.1

    return primary


# ---------------------------------------------------------------------------
# Streak modifier
# ---------------------------------------------------------------------------

def get_streak_modifier(streak_count: int) -> float:
    """Return the streak multiplier for a given streak count."""
    if streak_count >= 60:
        return 1.30
    if streak_count >= 30:
        return 1.20
    if streak_count >= 14:
        return 1.15
    if streak_count >= 7:
        return 1.10
    if streak_count >= 3:
        return 1.05
    return 1.00


# ---------------------------------------------------------------------------
# Late modifier
# ---------------------------------------------------------------------------

# Outer key: late_rule_behavior; inner key: timing band → modifier
_LATE_TABLE: dict[str, dict[str, float]] = {
    "Penalty": {
        "on_time":         1.00,
        "soft":            0.90,
        "meaningful_delay": 0.75,
        "hard_failure":    0.50,
        "void":            0.00,
    },
    "Incentive": {
        "on_time":         1.00,
        "soft":            1.10,
        "meaningful_delay": 1.20,
        "hard_failure":    1.25,
        # "void" is not defined for Incentive — treat as on_time (no penalty)
        "void":            1.00,
    },
    "Neutral": {
        "on_time":         1.00,
        "soft":            1.00,
        "meaningful_delay": 0.95,
        "hard_failure":    0.90,
        "void":            1.00,
    },
}


def get_late_modifier(completion_time: str, late_rule_behavior: str) -> float:
    """
    Return the late modifier for a given timing band and behavior type.

    completion_time must be one of:
        'on_time' | 'soft' | 'meaningful_delay' | 'hard_failure' | 'void'
    late_rule_behavior must be one of:
        'Penalty' | 'Incentive' | 'Neutral'

    Defaults to 1.00 on unknown inputs.
    """
    behavior_table = _LATE_TABLE.get(late_rule_behavior, {})
    return behavior_table.get(completion_time, 1.00)


# ---------------------------------------------------------------------------
# Crossover factor
# ---------------------------------------------------------------------------

_CROSSOVER_FACTORS: dict[str, float] = {
    "Indirect": 0.25,
    "Partial":  0.50,
    "Direct":   1.00,
}


def get_crossover_factor(crossover_level: str) -> float:
    """Return the skill XP multiplier for a crossover level."""
    return _CROSSOVER_FACTORS.get(crossover_level, 1.00)


# ---------------------------------------------------------------------------
# Step MH bonus
# ---------------------------------------------------------------------------

def get_step_mh_bonus(step_count: int) -> int:
    """Return the MH bonus for the highest completed step band."""
    if step_count >= 12000:
        return 5
    if step_count >= 10000:
        return 3
    if step_count >= 8000:
        return 2
    if step_count >= 4000:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Substance / leisure deltas
# ---------------------------------------------------------------------------

# Maps (event_type, name, quantity_threshold) → (gold_delta, mh_delta)
# For substance events the quantity check is done in code below.
_SUBSTANCE_DELTAS: dict[str, dict] = {
    "cigarette":          {"gold_delta": -2,  "mh_delta": -1},
    "alcohol_single":     {"gold_delta": -3,  "mh_delta": +1},   # 1 drink
    "alcohol_heavy":      {"gold_delta": -6,  "mh_delta": -3},   # 3+ drinks
    "caffeine_moderate":  {"gold_delta":  0,  "mh_delta":  0},
    "day_off":            {"gold_delta": -18, "mh_delta": +10},
    "cheat_day":          {"gold_delta": -24, "mh_delta": +15},
}


def get_substance_deltas(name: str, quantity: int) -> dict:
    """
    Return {"gold_delta": int, "mh_delta": int} for a substance/leisure event.

    name is matched case-insensitively against known substances.
    For alcohol, quantity determines single vs heavy tier.
    Returns zero deltas for unrecognised names.
    """
    key = name.lower().strip()

    if key == "cigarette":
        return dict(_SUBSTANCE_DELTAS["cigarette"])
    if key == "alcohol":
        tier = "alcohol_heavy" if quantity >= 3 else "alcohol_single"
        return dict(_SUBSTANCE_DELTAS[tier])
    if key == "caffeine":
        return dict(_SUBSTANCE_DELTAS["caffeine_moderate"])
    if key == "day_off":
        return dict(_SUBSTANCE_DELTAS["day_off"])
    if key == "cheat_day":
        return dict(_SUBSTANCE_DELTAS["cheat_day"])

    # Unknown substance — no delta
    return {"gold_delta": 0, "mh_delta": 0}


# ---------------------------------------------------------------------------
# Skill decay threshold
# ---------------------------------------------------------------------------

_DECAY_THRESHOLDS: dict[str, int] = {
    "Slow":   30,
    "Medium": 14,
    "Fast":   7,
}


def get_decay_threshold(decay_rate: str) -> int:
    """Return days-inactive threshold before decay triggers."""
    return _DECAY_THRESHOLDS.get(decay_rate, 14)  # default to Medium


# ---------------------------------------------------------------------------
# Reward formula
# ---------------------------------------------------------------------------

def calculate_rewards(
    base_xp: int,
    base_gold: int,
    arc_modifier: float,
    streak_modifier: float,
    late_modifier: float,
    partial_credit: float,
) -> dict:
    """
    Apply the full modifier stack and return final reward values.

    final_xp   = round(base_xp   × arc × streak × late × partial)
    final_gold = round(base_gold × arc          × late × partial)

    Streak does NOT apply to gold (per shared context formula).
    Effects add flat offsets after the stack — handled by the caller.
    """
    final_xp = round(base_xp * arc_modifier * streak_modifier * late_modifier * partial_credit)
    final_gold = round(base_gold * arc_modifier * late_modifier * partial_credit)
    return {"final_xp": final_xp, "final_gold": final_gold}
