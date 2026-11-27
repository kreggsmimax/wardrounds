"""Simulate publishing N days against the real ledger using a throwaway history file.

Proves the cooldown blocks repeats without touching output/history.
"""
import json
import pathlib
import tempfile

from engine import facts, script, verify

tmp = pathlib.Path(tempfile.mkdtemp()) / "used.json"
tmp.write_text('{"used": []}', encoding="utf-8")

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
for day in range(1, 11):
    used = facts.recent_ids(21, tmp)
    try:
        picked = facts.pick(valid, 3, used_ids=used, strict=True, seed=day,
                            history_path=tmp)
    except Exception as exc:  # noqa: BLE001
        print(f"day {day}: STOPPED -> {exc}")
        break
    topics = [p["topic"][:34] for p in picked]
    clash = [t for t in topics if t in seen]
    print(f"day {day}: {topics}  repeats={clash or 'none'}")
    seen.update(topics)
    facts.record_used(picked, tmp)
