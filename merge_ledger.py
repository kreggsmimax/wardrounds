"""Rebuild data/questions.json from the two sides of a merge conflict, union by id.

Works directly from git objects, so it is safe even if the working file currently
contains conflict markers.
"""
import json
import subprocess
import sys


def show(rev: str) -> dict:
    raw = subprocess.run(
        ["git", "show", f"{rev}:data/questions.json"],
        capture_output=True, check=True,
    ).stdout.decode("utf-8")
    return json.loads(raw)


ours_rev, theirs_rev = sys.argv[1], sys.argv[2]
ours, theirs = show(ours_rev), show(theirs_rev)

merged: dict[str, dict] = {}
for entry in theirs.get("questions", []):
    merged[entry["id"]] = entry
for entry in ours.get("questions", []):
    prev = merged.get(entry["id"])
    if prev is None or len(json.dumps(entry)) > len(json.dumps(prev)):
        merged[entry["id"]] = entry

out = {
    "version": max(ours.get("version", 1), theirs.get("version", 1)),
    "_comment": theirs.get("_comment") or ours.get("_comment", ""),
    "questions": list(merged.values()),
}
with open("data/questions.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2, ensure_ascii=False)
    fh.write("\n")

print(f"ours={len(ours.get('questions', []))}  theirs={len(theirs.get('questions', []))}  "
      f"merged={len(merged)}")
