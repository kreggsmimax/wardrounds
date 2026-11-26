"""
The gate.

Two layers:
  1. Structural  - the ledger entry is complete and internally consistent (facts.validate)
  2. Fidelity    - every number the reviewer signed off actually survives into the
                   narration, and no scene is malformed

Layer 2 is the one that matters. It catches the failure mode that kills medical
channels: a value silently dropped or altered between the approved ledger and the
spoken script.
"""

from __future__ import annotations

import re

import config as C
from engine import facts

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    return {m.group(0).rstrip(".,") for m in NUM.finditer(text) if len(m.group(0)) > 0}


def check_entry(entry: dict) -> list[str]:
    issues: list[str] = []
    try:
        facts.validate(entry)
    except facts.LedgerError as exc:
        issues.append(f"structure: {exc}")
        return issues

    if len(entry["vignette"].split()) < 20:
        issues.append(f"{entry['id']}: vignette under 20 words, thin for a step 1 stem")
    if len(entry["vignette"].split()) > 190:
        issues.append(f"{entry['id']}: vignette over 190 words, will not fit on screen")
    stem = entry["stem"].strip()
    if not stem.endswith("?"):
        issues.append(f"{entry['id']}: stem does not end with a question")
    if len(stem.split()) < 8:
        issues.append(f"{entry['id']}: stem under 8 words, too terse to test reasoning")
    if entry["review"]["status"] != "approved":
        issues.append(f"{entry['id']}: not approved, will not render")
    return issues


def check_scenes(scenes: list[dict], entry: dict,
                 vignette: str | None = None,
                 include_options: bool = True) -> list[str]:
    """Verify the generated narration preserves the approved facts.

    Pass `vignette` to check a condensed variant (the Shorts cut) against its own
    approved text. Set `include_options=False` for cuts that do not walk the
    distractors - otherwise the check demands numbers the format never speaks.
    """
    issues: list[str] = []
    spoken = " ".join(s.get("narration", "") for s in scenes if s.get("narration"))

    parts = [vignette or entry["vignette"], entry["stem"], entry["rule"]]
    if include_options:
        for o in entry["options"]:
            # the correct option's "would_make_right" is never narrated, and for the
            # right answer the field is contradictory anyway
            parts.append(o["text"] + " " + o["why"])
            if not o["correct"]:
                parts.append(o["would_make_right"])
    source = " ".join(parts)

    missing = numbers_in(source) - numbers_in(spoken)
    if missing:
        issues.append(f"{entry['id']}: numbers dropped from narration: {sorted(missing)}")

    for i, scene in enumerate(scenes):
        if scene["kind"] == "pause":
            continue
        narration = scene.get("narration", "")
        if not narration.strip():
            issues.append(f"{entry['id']}: scene {i} ({scene['kind']}) has no narration")
        if len(narration) > 900:
            issues.append(f"{entry['id']}: scene {i} narration over 900 chars, split it")

    return issues


def check_video(scenes: list[dict], entries: list[dict]) -> list[str]:
    issues: list[str] = []
    for entry in entries:
        issues.extend(check_entry(entry))

    # split the flat scene list into one group per question
    groups: list[list[dict]] = []
    current: list[dict] = []
    for scene in scenes:
        starts_question = (scene["kind"] in ("titlecard", "statement")
                           and str(scene.get("kicker", "")).startswith("QUESTION"))
        if starts_question:
            if current:
                groups.append(current)
            current = [scene]
        elif current:
            current.append(scene)
    if current:
        groups.append(current)

    if len(groups) != len(entries):
        issues.append(f"scene grouping mismatch: {len(groups)} groups for {len(entries)} questions")

    for group, entry in zip(groups, entries):
        issues.extend(check_scenes(group, entry))

    if not any(s["kind"] == "pause" for s in scenes):
        issues.append("no pause card in the video")
    if sum(1 for s in scenes if s["kind"] == "pause") < len(entries):
        issues.append("fewer pause cards than questions")
    return issues


def require_clean(scenes: list[dict], entries: list[dict]) -> None:
    issues = check_video(scenes, entries)
    if issues:
        raise SystemExit(
            "VERIFICATION FAILED - refusing to render:\n  " + "\n  ".join(issues)
        )
    print(f"  verify: clean ({len(entries)} questions, {len(scenes)} scenes)")
