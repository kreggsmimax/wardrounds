"""Simulate 8 days of publishing and prove the cooldown actually blocks repeats."""
import pathlib
import tempfile

from engine import facts, script, verify

tmp = pathlib.Path(tempfile.mkdtemp()) / "used.json"
facts.HISTORY = tmp

everything = facts.load(approved_only=False)
approved = [e for e in everything if e["review"]["status"] == "approved"]

valid = []
for entry in approved:
    issues = verify.check_entry(entry)
    if not issues:
        issues = verify.check_scenes(script.question_scenes(entry, 1, 1), entry)
    if not issues:
        valid.append(entry)

print(f"approved {len(approved)}  valid {len(valid)}")
seen: set[str] = set()
for day in range(1, 9):
    used = facts.recent_ids(21)
    try:
        picked = facts.pick(valid, 3, used_ids=used, strict=True, seed=day)
    except Exception as exc:  # noqa: BLE001
        print(f"day {day}: STOPPED -> {exc}")
        break
    topics = [p["topic"][:40] for p in picked]
    clash = [t for t in topics if t in seen]
    print(f"day {day}: {topics}  repeats={clash or 'none'}")
    seen.update(topics)
    facts.record_used(picked)
