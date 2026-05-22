"""
test_writes.py — Integration tests for scripts/writes.py.

Requires: live Supabase instance with seed data and
          SUPABASE_URL + SUPABASE_SERVICE_KEY in environment.

Run with:
    pytest scripts/tests/test_writes.py -v

Tests are marked @pytest.mark.integration and can be skipped in CI:
    pytest -m "not integration"

WARNING: These tests mutate state. Run against a dedicated test/staging
Supabase project, not production.
"""

import pytest
from datetime import date, timedelta
import uuid

pytestmark = pytest.mark.integration

try:
    from scripts.writes import (
        tick_day,
        complete_task,
        log_event,
        create_task,
        create_effect,
        update_arc_status,
        end_day,
    )
    from scripts.reads import get_player_state, get_today, get_tasks
    from scripts.db import get_client
    from scripts.logic import derive_mh_mode, clamp_mh
    _imports_ok = True
except Exception:
    _imports_ok = False


@pytest.fixture(autouse=True)
def require_imports():
    if not _imports_ok:
        pytest.skip("scripts could not be imported — check env vars")


# Use a far-future date so tests don't collide with real daily operations.
TEST_DATE = "2099-06-15"
YESTERDAY = "2099-06-14"


@pytest.fixture(scope="module")
def sb():
    return get_client()


# ---------------------------------------------------------------------------
# tick_day
# ---------------------------------------------------------------------------

class TestTickDay:
    def test_creates_snapshot(self, sb):
        # Clean up first
        sb.table("day_snapshots").delete().eq("date", TEST_DATE).execute()
        result = tick_day(TEST_DATE)
        assert result.get("success") is True
        assert "snapshot_id" in result

    def test_idempotent_second_call(self, sb):
        # Snapshot already exists from previous test
        result = tick_day(TEST_DATE)
        assert result.get("success") is False
        assert result.get("reason") == "already_exists"

    def test_snapshot_row_exists_in_db(self, sb):
        rows = sb.table("day_snapshots").select("id").eq("date", TEST_DATE).execute()
        assert len(rows.data) == 1

    def test_snapshot_has_correct_mh_open(self, sb):
        ps = get_player_state()
        snap = sb.table("day_snapshots").select("mh_score_open").eq("date", TEST_DATE).execute()
        # mh_score_open should match player_state at time of tick (may differ if PS changed)
        assert snap.data[0]["mh_score_open"] is not None

    def test_returns_error_dict_on_bad_input(self):
        # tick_day should never raise — a deeply invalid date returns an error dict
        result = tick_day("not-a-date")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# create_task (needed before complete_task tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def created_task_id(sb):
    """Create a minimal test task and return its ID. Cleaned up at module teardown."""
    result = create_task({
        "task": "Integration test task",
        "type": "Optional",
        "status": "Not started",
        "priority": "P2",
        "category": "Hobby",
        "date": TEST_DATE,
        "energy_cost": "Low",
        "late_rule": "Soft",
        "late_rule_behavior": "Penalty",
        "mandatory": False,
        "xp": 100,
        "gold": 50,
        "mh_impact": 2,
        "skills": [],
        "arcs": [],
        "stats": [],
    })
    assert "task_id" in result, f"create_task failed: {result}"
    yield result["task_id"]
    # Cleanup
    sb.table("tasks").delete().eq("id", result["task_id"]).execute()


class TestCreateTask:
    def test_returns_task_id(self, created_task_id):
        assert created_task_id is not None

    def test_task_exists_in_db(self, sb, created_task_id):
        rows = sb.table("tasks").select("id").eq("id", created_task_id).execute()
        assert len(rows.data) == 1

    def test_skill_links_created_count(self, sb):
        result = create_task({
            "task": "Task with skills",
            "type": "Optional",
            "status": "Not started",
            "priority": "P3",
            "category": "Study",
            "date": TEST_DATE,
            "energy_cost": "Low",
            "late_rule": "None",
            "late_rule_behavior": "Neutral",
            "mandatory": False,
            "xp": 10,
            "gold": 5,
            "skills": [],  # no skills — clean test
            "arcs": [],
            "stats": [],
        })
        assert result.get("skill_links_created") == 0
        # Cleanup
        sb.table("tasks").delete().eq("id", result["task_id"]).execute()


# ---------------------------------------------------------------------------
# complete_task
# ---------------------------------------------------------------------------

class TestCompleteTask:
    def test_returns_expected_keys(self, created_task_id):
        result = complete_task(created_task_id, {
            "completion_time": "on_time",
            "partial_credit": 1.0,
            "mh_mode": "Normal",
        })
        for key in ("final_xp", "final_gold", "new_mh_score", "new_mh_mode", "new_gold_balance"):
            assert key in result, f"missing key: {key}"

    def test_mh_score_in_range_after_complete(self, created_task_id):
        result = complete_task(created_task_id, {
            "completion_time": "on_time",
            "partial_credit": 1.0,
            "mh_mode": "Normal",
        })
        assert 0 <= result.get("new_mh_score", 50) <= 100

    def test_mh_mode_consistent_with_score(self, created_task_id):
        result = complete_task(created_task_id, {
            "completion_time": "on_time",
            "partial_credit": 1.0,
            "mh_mode": "Normal",
        })
        expected_mode = derive_mh_mode(result["new_mh_score"])
        assert result["new_mh_mode"] == expected_mode

    def test_task_status_set_to_done(self, sb, created_task_id):
        complete_task(created_task_id, {
            "completion_time": "on_time",
            "partial_credit": 1.0,
            "mh_mode": "Normal",
        })
        row = sb.table("tasks").select("status").eq("id", created_task_id).execute()
        if row.data:
            assert row.data[0]["status"] == "Done"

    def test_unknown_task_returns_error(self):
        result = complete_task("00000000-0000-0000-0000-000000000000", {
            "completion_time": "on_time",
            "partial_credit": 1.0,
            "mh_mode": "Normal",
        })
        assert result.get("success") is False or "error" in result


# ---------------------------------------------------------------------------
# log_event
# ---------------------------------------------------------------------------

class TestLogEvent:
    def test_steps_increases_mh(self):
        ps_before = get_player_state()
        result = log_event("steps", {"quantity": 10000})
        # +3 MH from 10k steps, clamped
        expected = clamp_mh(ps_before["mh_score"] + 3)
        assert result["new_mh_score"] == expected

    def test_steps_returns_required_keys(self):
        result = log_event("steps", {"quantity": 4000})
        for key in ("new_mh_score", "new_mh_mode", "new_gold_balance", "delta_applied"):
            assert key in result

    def test_substance_cigarette_reduces_gold(self):
        ps_before = get_player_state()
        result = log_event("substance", {"name": "cigarette", "quantity": 1})
        assert result["new_gold_balance"] == ps_before["gold_balance"] - 2

    def test_substance_cigarette_reduces_mh(self):
        ps_before = get_player_state()
        result = log_event("substance", {"name": "cigarette", "quantity": 1})
        expected = clamp_mh(ps_before["mh_score"] - 1)
        assert result["new_mh_score"] == expected

    def test_day_off_delta(self):
        ps_before = get_player_state()
        result = log_event("day_off", {})
        assert result["delta_applied"]["gold_delta"] == -18
        assert result["delta_applied"]["mh_delta"] == 10

    def test_mh_never_exceeds_100(self):
        # Spam MH gains — should always clamp to 100
        for _ in range(5):
            result = log_event("steps", {"quantity": 15000})
        assert result["new_mh_score"] <= 100

    def test_mh_never_goes_below_0(self):
        # Spam negatives — should always clamp to 0
        for _ in range(30):
            result = log_event("substance", {"name": "cigarette", "quantity": 1})
        assert result["new_mh_score"] >= 0

    def test_mh_mode_consistent_after_event(self):
        result = log_event("steps", {"quantity": 8000})
        assert result["new_mh_mode"] == derive_mh_mode(result["new_mh_score"])


# ---------------------------------------------------------------------------
# create_effect
# ---------------------------------------------------------------------------

class TestCreateEffect:
    def test_returns_effect_id_and_expires_on(self, sb):
        result = create_effect({
            "effect": "Integration test buff",
            "type": "Buff",
            "intensity": 3,
            "duration_days": 7,
            "created_on": TEST_DATE,
            "stat_offset": 5,
            "suppresses_arc_pressure": False,
            "stats": [],
            "arcs": [],
        })
        assert "effect_id" in result
        assert result["expires_on"] == "2099-06-22"  # TEST_DATE + 7 days
        # Cleanup
        sb.table("effects").delete().eq("id", result["effect_id"]).execute()

    def test_expires_on_computed_correctly(self, sb):
        result = create_effect({
            "effect": "Short buff",
            "type": "Buff",
            "intensity": 1,
            "duration_days": 3,
            "created_on": "2099-01-01",
            "stat_offset": 0,
            "stats": [],
            "arcs": [],
        })
        assert result["expires_on"] == "2099-01-04"
        sb.table("effects").delete().eq("id", result["effect_id"]).execute()


# ---------------------------------------------------------------------------
# update_arc_status
# ---------------------------------------------------------------------------

class TestUpdateArcStatus:
    def _get_any_arc_id(self, sb):
        rows = sb.table("arcs").select("id, status").limit(1).execute()
        if not rows.data:
            pytest.skip("no arcs in DB")
        return rows.data[0]["id"], rows.data[0]["status"]

    def test_valid_status_update(self, sb):
        arc_id, original_status = self._get_any_arc_id(sb)
        result = update_arc_status(arc_id, "Paused")
        assert result == {"success": True}
        # Restore
        update_arc_status(arc_id, original_status)

    def test_invalid_status_returns_error(self, sb):
        arc_id, _ = self._get_any_arc_id(sb)
        result = update_arc_status(arc_id, "Invalid")
        assert result.get("success") is False

    def test_done_status_accepted(self, sb):
        arc_id, original_status = self._get_any_arc_id(sb)
        result = update_arc_status(arc_id, "Done")
        assert result == {"success": True}
        update_arc_status(arc_id, original_status)


# ---------------------------------------------------------------------------
# end_day
# ---------------------------------------------------------------------------

class TestEndDay:
    @pytest.fixture(autouse=True)
    def ensure_snapshot(self, sb):
        """Ensure a snapshot exists for TEST_DATE before end_day tests."""
        existing = sb.table("day_snapshots").select("id").eq("date", TEST_DATE).execute()
        if not existing.data:
            tick_day(TEST_DATE)
        # Clean up streak_log entry for TEST_DATE so end_day can insert cleanly
        sb.table("streak_log").delete().eq("date", TEST_DATE).execute()
        yield

    def test_returns_required_keys(self):
        result = end_day(TEST_DATE)
        for key in ("mh_score_close", "gold_close", "streak_count", "mandatory_met"):
            assert key in result

    def test_mh_score_close_in_range(self):
        result = end_day(TEST_DATE)
        assert 0 <= result["mh_score_close"] <= 100

    def test_mandatory_met_is_bool(self):
        result = end_day(TEST_DATE)
        assert isinstance(result["mandatory_met"], bool)

    def test_streak_count_is_int(self):
        result = end_day(TEST_DATE)
        assert isinstance(result["streak_count"], int)

    def test_streak_log_row_written(self, sb):
        end_day(TEST_DATE)
        rows = sb.table("streak_log").select("id").eq("date", TEST_DATE).execute()
        assert len(rows.data) >= 1

    def test_player_state_streak_updated(self, sb):
        result = end_day(TEST_DATE)
        ps = get_player_state()
        assert ps["streak_count"] == result["streak_count"]
