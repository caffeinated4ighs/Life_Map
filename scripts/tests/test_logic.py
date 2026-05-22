"""
test_logic.py — Unit tests for scripts/logic.py.

All pure functions. No DB, no mocks. Run with:
    pytest scripts/tests/test_logic.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from scripts.logic import (
    derive_mh_mode,
    clamp_mh,
    get_arc_modifier,
    get_streak_modifier,
    get_late_modifier,
    get_crossover_factor,
    get_step_mh_bonus,
    get_substance_deltas,
    get_decay_threshold,
    calculate_rewards,
)


# ---------------------------------------------------------------------------
# derive_mh_mode
# ---------------------------------------------------------------------------

class TestDeriveMhMode:
    def test_normal_boundary(self):
        assert derive_mh_mode(80) == "Normal"

    def test_normal_upper(self):
        assert derive_mh_mode(100) == "Normal"

    def test_reduced_boundary(self):
        assert derive_mh_mode(60) == "Reduced"

    def test_reduced_upper(self):
        assert derive_mh_mode(79) == "Reduced"

    def test_minimum_viable_boundary(self):
        assert derive_mh_mode(40) == "Minimum Viable"

    def test_minimum_viable_upper(self):
        assert derive_mh_mode(59) == "Minimum Viable"

    def test_recovery_only_boundary(self):
        assert derive_mh_mode(39) == "Recovery Only"

    def test_recovery_only_zero(self):
        assert derive_mh_mode(0) == "Recovery Only"


# ---------------------------------------------------------------------------
# clamp_mh
# ---------------------------------------------------------------------------

class TestClampMh:
    def test_within_range(self):
        assert clamp_mh(50) == 50

    def test_zero(self):
        assert clamp_mh(0) == 0

    def test_hundred(self):
        assert clamp_mh(100) == 100

    def test_below_zero(self):
        assert clamp_mh(-10) == 0

    def test_above_hundred(self):
        assert clamp_mh(110) == 100

    def test_exactly_minus_one(self):
        assert clamp_mh(-1) == 0

    def test_exactly_101(self):
        assert clamp_mh(101) == 100


# ---------------------------------------------------------------------------
# get_arc_modifier
# ---------------------------------------------------------------------------

class TestGetArcModifier:
    def test_empty_returns_normal(self):
        assert get_arc_modifier([]) == 1.00

    def test_single_background(self):
        assert get_arc_modifier(["Background"]) == 0.80

    def test_single_normal(self):
        assert get_arc_modifier(["Normal"]) == 1.00

    def test_single_focused(self):
        assert get_arc_modifier(["Focused"]) == 1.25

    def test_single_critical(self):
        assert get_arc_modifier(["Critical"]) == 1.50

    def test_two_same_weights_no_bonus(self):
        # Same weight — no secondary bonus
        assert get_arc_modifier(["Focused", "Focused"]) == 1.25

    def test_two_different_weights_adds_bonus(self):
        # Critical primary + Normal secondary → 1.50 + 0.1
        result = get_arc_modifier(["Normal", "Critical"])
        assert result == pytest.approx(1.60)

    def test_secondary_bonus_max_0_1(self):
        result = get_arc_modifier(["Critical", "Background"])
        assert result == pytest.approx(1.60)

    def test_order_independent(self):
        a = get_arc_modifier(["Focused", "Background"])
        b = get_arc_modifier(["Background", "Focused"])
        assert a == b

    def test_three_weights_still_uses_primary_plus_one_bonus(self):
        result = get_arc_modifier(["Background", "Normal", "Critical"])
        # Primary = Critical (1.50) + 0.1 bonus (secondary = Normal ≠ Critical)
        assert result == pytest.approx(1.60)


# ---------------------------------------------------------------------------
# get_streak_modifier
# ---------------------------------------------------------------------------

class TestGetStreakModifier:
    def test_zero(self):
        assert get_streak_modifier(0) == 1.00

    def test_two_days(self):
        assert get_streak_modifier(2) == 1.00

    def test_three_days(self):
        assert get_streak_modifier(3) == 1.05

    def test_six_days(self):
        assert get_streak_modifier(6) == 1.05

    def test_seven_days(self):
        assert get_streak_modifier(7) == 1.10

    def test_thirteen_days(self):
        assert get_streak_modifier(13) == 1.10

    def test_fourteen_days(self):
        assert get_streak_modifier(14) == 1.15

    def test_twenty_nine_days(self):
        assert get_streak_modifier(29) == 1.15

    def test_thirty_days(self):
        assert get_streak_modifier(30) == 1.20

    def test_fifty_nine_days(self):
        assert get_streak_modifier(59) == 1.20

    def test_sixty_days(self):
        assert get_streak_modifier(60) == 1.30

    def test_one_hundred_days_hard_cap(self):
        assert get_streak_modifier(100) == 1.30


# ---------------------------------------------------------------------------
# get_late_modifier
# ---------------------------------------------------------------------------

class TestGetLateModifier:
    # Penalty column
    def test_penalty_on_time(self):
        assert get_late_modifier("on_time", "Penalty") == 1.00

    def test_penalty_soft(self):
        assert get_late_modifier("soft", "Penalty") == 0.90

    def test_penalty_meaningful_delay(self):
        assert get_late_modifier("meaningful_delay", "Penalty") == 0.75

    def test_penalty_hard_failure(self):
        assert get_late_modifier("hard_failure", "Penalty") == 0.50

    def test_penalty_void(self):
        assert get_late_modifier("void", "Penalty") == 0.00

    # Incentive column
    def test_incentive_on_time(self):
        assert get_late_modifier("on_time", "Incentive") == 1.00

    def test_incentive_soft(self):
        assert get_late_modifier("soft", "Incentive") == 1.10

    def test_incentive_meaningful_delay(self):
        assert get_late_modifier("meaningful_delay", "Incentive") == 1.20

    def test_incentive_hard_failure_cap(self):
        assert get_late_modifier("hard_failure", "Incentive") == 1.25

    # Neutral column
    def test_neutral_on_time(self):
        assert get_late_modifier("on_time", "Neutral") == 1.00

    def test_neutral_soft(self):
        assert get_late_modifier("soft", "Neutral") == 1.00

    def test_neutral_meaningful_delay(self):
        assert get_late_modifier("meaningful_delay", "Neutral") == 0.95

    def test_neutral_hard_failure(self):
        assert get_late_modifier("hard_failure", "Neutral") == 0.90

    def test_unknown_behavior_defaults_to_1(self):
        assert get_late_modifier("on_time", "Unknown") == 1.00

    def test_unknown_timing_defaults_to_1(self):
        assert get_late_modifier("unknown_band", "Penalty") == 1.00


# ---------------------------------------------------------------------------
# get_crossover_factor
# ---------------------------------------------------------------------------

class TestGetCrossoverFactor:
    def test_indirect(self):
        assert get_crossover_factor("Indirect") == 0.25

    def test_partial(self):
        assert get_crossover_factor("Partial") == 0.50

    def test_direct(self):
        assert get_crossover_factor("Direct") == 1.00

    def test_unknown_defaults_to_1(self):
        assert get_crossover_factor("Nonexistent") == 1.00


# ---------------------------------------------------------------------------
# get_step_mh_bonus
# ---------------------------------------------------------------------------

class TestGetStepMhBonus:
    def test_zero_steps(self):
        assert get_step_mh_bonus(0) == 0

    def test_below_4000(self):
        assert get_step_mh_bonus(3999) == 0

    def test_exactly_4000(self):
        assert get_step_mh_bonus(4000) == 1

    def test_between_4000_and_8000(self):
        assert get_step_mh_bonus(6000) == 1

    def test_exactly_8000(self):
        assert get_step_mh_bonus(8000) == 2

    def test_exactly_10000(self):
        assert get_step_mh_bonus(10000) == 3

    def test_between_10000_and_12000(self):
        assert get_step_mh_bonus(11000) == 3

    def test_exactly_12000(self):
        assert get_step_mh_bonus(12000) == 5

    def test_above_12000(self):
        assert get_step_mh_bonus(15000) == 5


# ---------------------------------------------------------------------------
# get_substance_deltas
# ---------------------------------------------------------------------------

class TestGetSubstanceDeltas:
    def test_cigarette(self):
        d = get_substance_deltas("cigarette", 1)
        assert d == {"gold_delta": -2, "mh_delta": -1}

    def test_cigarette_case_insensitive(self):
        d = get_substance_deltas("Cigarette", 1)
        assert d["gold_delta"] == -2

    def test_alcohol_single(self):
        d = get_substance_deltas("alcohol", 1)
        assert d == {"gold_delta": -3, "mh_delta": 1}

    def test_alcohol_two_drinks_still_single(self):
        d = get_substance_deltas("alcohol", 2)
        assert d == {"gold_delta": -3, "mh_delta": 1}

    def test_alcohol_heavy(self):
        d = get_substance_deltas("alcohol", 3)
        assert d == {"gold_delta": -6, "mh_delta": -3}

    def test_alcohol_heavy_more(self):
        d = get_substance_deltas("alcohol", 5)
        assert d == {"gold_delta": -6, "mh_delta": -3}

    def test_caffeine(self):
        d = get_substance_deltas("caffeine", 1)
        assert d == {"gold_delta": 0, "mh_delta": 0}

    def test_day_off(self):
        d = get_substance_deltas("day_off", 1)
        assert d == {"gold_delta": -18, "mh_delta": 10}

    def test_cheat_day(self):
        d = get_substance_deltas("cheat_day", 1)
        assert d == {"gold_delta": -24, "mh_delta": 15}

    def test_unknown_substance(self):
        d = get_substance_deltas("mystery_pill", 1)
        assert d == {"gold_delta": 0, "mh_delta": 0}


# ---------------------------------------------------------------------------
# get_decay_threshold
# ---------------------------------------------------------------------------

class TestGetDecayThreshold:
    def test_slow(self):
        assert get_decay_threshold("Slow") == 30

    def test_medium(self):
        assert get_decay_threshold("Medium") == 14

    def test_fast(self):
        assert get_decay_threshold("Fast") == 7

    def test_unknown_defaults_to_medium(self):
        assert get_decay_threshold("Unknown") == 14


# ---------------------------------------------------------------------------
# calculate_rewards
# ---------------------------------------------------------------------------

class TestCalculateRewards:
    def test_no_modifiers(self):
        r = calculate_rewards(100, 50, 1.0, 1.0, 1.0, 1.0)
        assert r == {"final_xp": 100, "final_gold": 50}

    def test_streak_does_not_affect_gold(self):
        r = calculate_rewards(100, 50, 1.0, 1.30, 1.0, 1.0)
        assert r["final_xp"] == 130
        assert r["final_gold"] == 50  # streak doesn't multiply gold

    def test_arc_affects_both(self):
        r = calculate_rewards(100, 50, 1.50, 1.0, 1.0, 1.0)
        assert r["final_xp"] == 150
        assert r["final_gold"] == 75

    def test_late_penalty_affects_both(self):
        r = calculate_rewards(100, 50, 1.0, 1.0, 0.75, 1.0)
        assert r["final_xp"] == 75
        assert r["final_gold"] == 38  # round(50 * 0.75)

    def test_partial_credit(self):
        r = calculate_rewards(100, 50, 1.0, 1.0, 1.0, 0.5)
        assert r["final_xp"] == 50
        assert r["final_gold"] == 25

    def test_void_late_zeroes_xp_and_gold(self):
        r = calculate_rewards(100, 50, 1.0, 1.0, 0.0, 1.0)
        assert r["final_xp"] == 0
        assert r["final_gold"] == 0

    def test_full_stack(self):
        # base_xp=200, arc=1.25, streak=1.10, late=0.90, partial=0.8
        # xp = round(200 * 1.25 * 1.10 * 0.90 * 0.80) = round(198.0) = 198
        # gold = round(100 * 1.25 * 0.90 * 0.80) = round(90.0) = 90
        r = calculate_rewards(200, 100, 1.25, 1.10, 0.90, 0.80)
        assert r["final_xp"] == 198
        assert r["final_gold"] == 90

    def test_result_is_rounded(self):
        r = calculate_rewards(10, 10, 1.25, 1.05, 0.90, 1.0)
        assert isinstance(r["final_xp"], int)
        assert isinstance(r["final_gold"], int)
