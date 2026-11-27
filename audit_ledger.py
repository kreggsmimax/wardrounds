"""Report which ledger entries fail verification and why."""
from engine import facts, script, verify

entries = facts.load(approved_only=False)
bad = 0
for entry in entries:
    issues = verify.check_entry(entry)
    if not issues:
        issues = verify.check_scenes(script.question_scenes(entry, 1, 1), entry)
    if issues:
        bad += 1
        print(f"{entry['system']:10} {entry['topic'][:44]:46} {issues[0][:70]}")

print(f"\n{len(entries)} entries, {bad} fail verification, {len(entries) - bad} usable")
