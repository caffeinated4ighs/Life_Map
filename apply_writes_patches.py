"""
Apply CORE-006 and CORE-007 patches to scripts/writes.py in-place.
Run from repo root: python apply_writes_patches.py
"""

import pathlib, sys

target = pathlib.Path("scripts/writes.py")
if not target.exists():
    sys.exit(f"ERROR: {target} not found — run from repo root")

text = target.read_text()

# ── CORE-006 ──────────────────────────────────────────────────────────────────
# complete_task step 9 used task.get("date") — a late completion writes XP to
# the task's scheduled date rather than today.  Fix: always use today.
OLD_006 = """\
        # 9. Update day_snapshots xp_earned
        today_str = str(task.get("date", ""))
        if today_str:"""

NEW_006 = """\
        # 9. Update day_snapshots xp_earned
        # CORE-006: always use today's date so late completions update today's snapshot
        today_str = str(date_type.today())
        if today_str:"""

if OLD_006 not in text:
    sys.exit("CORE-006: target string not found — writes.py may already be patched or has changed")
text = text.replace(OLD_006, NEW_006, 1)
print("CORE-006 applied ✓")

# ── CORE-007 ──────────────────────────────────────────────────────────────────
# log_event hardcodes today_str = str(date_type.today()), ignoring payload["date"].
# Fix: honour the date param if provided so retroactive events are possible.
OLD_007 = """\
        today_str = str(date_type.today())
        name = payload.get("name", "")"""

NEW_007 = """\
        # CORE-007: honour date param from payload so retroactive events work
        today_str = payload.get("date", str(date_type.today()))
        name = payload.get("name", "")"""

if OLD_007 not in text:
    sys.exit("CORE-007: target string not found — writes.py may already be patched or has changed")
text = text.replace(OLD_007, NEW_007, 1)
print("CORE-007 applied ✓")

target.write_text(text)
print(f"\nPatched {target} successfully.")