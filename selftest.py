import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import facts

approved = facts.load()
pending = facts.load(approved_only=False)
approved_ids = {q["id"] for q in approved}

print("approved:", [q["id"] for q in approved])
print("total   :", len(pending))
print("blocked :", [q["id"] for q in pending if q["id"] not in approved_ids])
print()
for q in approved:
    print(f"  {q['id']:38s} ~{facts.estimate_seconds(q):5.0f}s  [{q['system']}]")
print()
print("pick 3:", [q["id"] for q in facts.pick(approved, 3, seed=7)])
print("pick 2 same-system:", [q["id"] for q in facts.pick(approved, 2, system="heme")])

# negative tests: the validator must reject these
def expect_fail(label, mutate):
    import copy, json
    raw = json.loads((Path(__file__).parent / "data" / "questions.json").read_text(encoding="utf-8"))
    entry = copy.deepcopy(raw["questions"][0])
    mutate(entry)
    try:
        facts.validate(entry)
    except facts.LedgerError as e:
        print(f"  OK  rejected {label}: {str(e)[:70]}")
    else:
        print(f"  FAIL accepted {label}")

print()
expect_fail("two correct answers", lambda e: e["options"][1].update(correct=True))
expect_fail("thin elimination text", lambda e: e["options"][2].update(would_make_right="n/a"))
expect_fail("approved without reviewer", lambda e: e["review"].update(by=""))
expect_fail("bad system", lambda e: e.update(system="astrology"))
