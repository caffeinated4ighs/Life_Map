"""
test_reads.py — Integration tests for scripts/reads.py.

Requires: live Supabase instance with seed data and
          SUPABASE_URL + SUPABASE_SERVICE_KEY in environment.

Run with:
    pytest scripts/tests/test_reads.py -v

All tests are marked with @pytest.mark.integration so they can be skipped
in CI without a live DB:
    pytest -m "not integration"
"""

import pytest
from datetime import date

pytestmark = pytest.mark.integration

# Import after marker — skip gracefully if env not set
try:
    from scripts.reads import (
        get_player_state,
        get_today,
        get_tasks,
        get_task,
        get_skill_links,
        get_active_effects,
        get_active_arcs,
    )
    _imports_ok = True
except Exception:
    _imports_ok = False


@pytest.fixture(autouse=True)
def require_imports():
    if not _imports_ok:
        pytest.skip("scripts.reads could not be imported — check env vars")


TODAY = str(date.today())


# ---------------------------------------------------------------------------
# get_player_state
# ---------------------------------------------------------------------------

class TestGetPlayerState:
    def test_returns_dict(self):
        result = get_player_state()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = get_player_state()
        for key in ("mh_score", "mh_mode", "gold_balance", "streak_count", "total_xp"):
            assert key in result, f"missing key: {key}"

    def test_mh_score_in_range(self):
        result = get_player_state()
        assert 0 <= result["mh_score"] <= 100

    def test_mh_mode_valid(self):
        result = get_player_state()
        valid = {"Normal", "Reduced", "Minimum Viable", "Recovery Only"}
        assert result["mh_mode"] in valid

    def test_singleton_is_consistent(self):
        a = get_player_state()
        b = get_player_state()
        assert a["mh_score"] == b["mh_score"]


# ---------------------------------------------------------------------------
# get_today
# ---------------------------------------------------------------------------

class TestGetToday:
    def test_returns_dict(self):
        result = get_today(TODAY)
        assert isinstance(result, dict)

    def test_has_needs_init_key(self):
        result = get_today(TODAY)
        assert "needs_init" in result

    def test_needs_init_is_bool(self):
        result = get_today(TODAY)
        assert isinstance(result["needs_init"], bool)

    def test_anchors_active_is_list(self):
        result = get_today(TODAY)
        assert isinstance(result.get("anchors_active", []), list)

    def test_far_future_date_needs_init(self):
        result = get_today("2099-01-01")
        assert result["needs_init"] is True

    def test_future_date_empty_anchors(self):
        result = get_today("2099-01-01")
        assert result["anchors_active"] == []


# ---------------------------------------------------------------------------
# get_tasks
# ---------------------------------------------------------------------------

class TestGetTasks:
    def test_returns_list(self):
        result = get_tasks(TODAY, "Normal")
        assert isinstance(result, list)

    def test_normal_mode_no_filtering(self):
        """Normal mode should include all non-done tasks."""
        result = get_tasks(TODAY, "Normal")
        for task in result:
            assert task["status"] not in ("Done",) if "status" in task else True

    def test_recovery_only_hides_non_mandatory_high_energy(self):
        all_tasks = get_tasks(TODAY, "Normal")
        recovery_tasks = get_tasks(TODAY, "Recovery Only")
        recovery_ids = {t["id"] for t in recovery_tasks}
        for task in all_tasks:
            if not task.get("mandatory") and task.get("energy_cost") in (
                "Low", "Medium", "High", "Very High"
            ):
                # Non-mandatory tasks should be hidden in Recovery Only
                assert task["id"] not in recovery_ids

    def test_recovery_only_keeps_mandatory(self):
        recovery_tasks = get_tasks(TODAY, "Recovery Only")
        normal_tasks = get_tasks(TODAY, "Normal")
        mandatory_normal = {t["id"] for t in normal_tasks if t.get("mandatory")}
        mandatory_recovery = {t["id"] for t in recovery_tasks}
        # All mandatory tasks from Normal mode should appear in Recovery Only
        assert mandatory_normal.issubset(mandatory_recovery)

    def test_reduced_hides_high_energy(self):
        reduced = get_tasks(TODAY, "Reduced")
        for task in reduced:
            if not task.get("mandatory"):
                assert task.get("energy_cost") not in ("High", "Very High")

    def test_tasks_have_required_keys(self):
        result = get_tasks(TODAY, "Normal")
        required = ("id", "task", "type", "priority", "xp", "gold", "mandatory")
        for task in result:
            for key in required:
                assert key in task, f"task missing key '{key}'"

    def test_tasks_include_arcs_and_skills_lists(self):
        result = get_tasks(TODAY, "Normal")
        for task in result:
            assert isinstance(task.get("arcs"), list)
            assert isinstance(task.get("skills"), list)


# ---------------------------------------------------------------------------
# get_task
# ---------------------------------------------------------------------------

class TestGetTask:
    def _get_any_task_id(self):
        tasks = get_tasks(TODAY, "Normal")
        if not tasks:
            pytest.skip("no tasks available for today")
        return tasks[0]["id"]

    def test_returns_dict_with_arc_modifier(self):
        task_id = self._get_any_task_id()
        result = get_task(task_id)
        assert "arc_modifier" in result

    def test_arc_modifier_is_float(self):
        task_id = self._get_any_task_id()
        result = get_task(task_id)
        assert isinstance(result["arc_modifier"], float)

    def test_suppression_active_is_bool(self):
        task_id = self._get_any_task_id()
        result = get_task(task_id)
        assert isinstance(result["suppression_active"], bool)

    def test_unknown_task_returns_empty(self):
        result = get_task("00000000-0000-0000-0000-000000000000")
        assert result == {}


# ---------------------------------------------------------------------------
# get_skill_links
# ---------------------------------------------------------------------------

class TestGetSkillLinks:
    def _get_task_with_skills(self):
        tasks = get_tasks(TODAY, "Normal")
        for task in tasks:
            if task.get("skills"):
                return task["id"]
        pytest.skip("no tasks with skill links found")

    def test_returns_list(self):
        result = get_skill_links("00000000-0000-0000-0000-000000000000")
        assert isinstance(result, list)

    def test_unknown_task_returns_empty(self):
        result = get_skill_links("00000000-0000-0000-0000-000000000000")
        assert result == []

    def test_skill_link_shape(self):
        task_id = self._get_task_with_skills()
        result = get_skill_links(task_id)
        assert len(result) > 0
        for link in result:
            assert "skill_id" in link
            assert "skill_name" in link
            assert "crossover_level" in link
            assert link["crossover_level"] in ("Indirect", "Partial", "Direct")


# ---------------------------------------------------------------------------
# get_active_effects
# ---------------------------------------------------------------------------

class TestGetActiveEffects:
    def test_returns_list(self):
        result = get_active_effects()
        assert isinstance(result, list)

    def test_effect_shape(self):
        result = get_active_effects()
        for eff in result:
            assert "effect" in eff
            assert "type" in eff
            assert "stat_offset" in eff
            assert "linked_stats" in eff
            assert isinstance(eff["linked_stats"], list)

    def test_type_is_valid(self):
        result = get_active_effects()
        for eff in result:
            assert eff["type"] in ("Buff", "Debuff")


# ---------------------------------------------------------------------------
# get_active_arcs
# ---------------------------------------------------------------------------

class TestGetActiveArcs:
    def test_returns_list(self):
        result = get_active_arcs()
        assert isinstance(result, list)

    def test_arc_shape(self):
        result = get_active_arcs()
        for arc in result:
            assert "arc" in arc
            assert "weight" in arc
            assert "skills_boosted" in arc
            assert isinstance(arc["skills_boosted"], list)

    def test_weight_is_valid(self):
        result = get_active_arcs()
        valid = {"Background", "Normal", "Focused", "Critical"}
        for arc in result:
            assert arc["weight"] in valid
