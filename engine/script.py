"""
Ledger entry -> list of scene specs.

Deterministic on purpose. Every clinical fact comes from the ledger; this module only
decides order, labels and narration phrasing. No model call is required to build a
video, which means the pipeline can run offline and a fact can never be invented here.
"""

from __future__ import annotations

import config as C


def _accent(entry: dict) -> tuple[int, int, int]:
    return C.SYSTEM_ACCENT.get(entry["system"], C.MUTED)


def _tag(entry: dict) -> str:
    return C.SYSTEM_LABEL.get(entry["system"], entry["system"].upper())


def _correct(entry: dict) -> dict:
    return next(o for o in entry["options"] if o["correct"])


def intro_scene(count: int, first: dict) -> dict:
    return {
        "kind": "titlecard",
        "tag": C.BRAND,
        "system": first["system"],
        "kicker": "USMLE STEP 1",
        "big": "QUESTION BANK",
        "sub": [C.TAGLINE, f"{count} questions · pause whenever you need to"],
        "narration": (
            f"This is {C.BRAND_SPOKEN}. Step 1, question by question. "
            f"Today's set has {count} questions. Pause whenever you need to, "
            f"and commit to an answer before the explanation."
        ),
    }


def _split_balanced(text: str, min_ratio: float = 0.35) -> list[str]:
    """Split a vignette into two frames at the sentence boundary that best balances
    them. A 7-line paragraph on one slide reads like a document; two 3-line frames
    read like a video."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) < 3:
        return [text]

    total = sum(len(s) for s in sentences)
    best_i, best_diff = 1, 1e9
    for i in range(1, len(sentences)):
        left = sum(len(s) for s in sentences[:i])
        if left < total * min_ratio:
            continue
        diff = abs(left - (total - left))
        if diff < best_diff:
            best_diff, best_i = diff, i

    return [" ".join(sentences[:best_i]), " ".join(sentences[best_i:])]


def question_scenes(entry: dict, number: int, total: int) -> list[dict]:
    accent = _accent(entry)
    tag = _tag(entry)
    correct = _correct(entry)
    scenes: list[dict] = []

    # 1 - hook card
    scenes.append({
        "kind": "titlecard",
        "tag": tag,
        "system": entry["system"],
        "kicker": f"QUESTION {number} OF {total}",
        "big": entry["topic"],
        "sub": [entry["hook"]],
        "narration": (
            f"{entry['hook']} This one is {tag.lower()}. "
            f"Question {number} of {total}."
        ),
    })

    # 2 - the vignette, split across two frames
    chunks = _split_balanced(entry["vignette"])
    for i, chunk in enumerate(chunks):
        scenes.append({
            "kind": "prose",
            "tag": tag,
            "system": entry["system"],
            "kicker": "THE VIGNETTE" if len(chunks) == 1 else
                      f"THE VIGNETTE {i + 1}/{len(chunks)}",
            "body": chunk,
            "size": 40,
            "narration": chunk,
        })

    # 3 - the decisive finding, huge. This is the frame people screenshot.
    if entry.get("key_finding"):
        scenes.append({
            "kind": "keyfind",
            "tag": tag,
            "system": entry["system"],
            "kicker": "THE FINDING THAT DECIDES IT",
            "body": entry["key_finding"],
            "narration": f"Here is the finding that decides it. {entry['key_finding']}",
        })

    # 3 - the stem
    scenes.append({
        "kind": "prose",
        "tag": tag,
        "system": entry["system"],
        "kicker": "THE QUESTION",
        "body": entry["stem"],
        "size": 42,
        "narration": entry["stem"],
    })

    # 4 - options
    scenes.append({
        "kind": "options",
        "tag": tag,
        "system": entry["system"],
        "kicker": "PICK YOUR ANSWER",
        "options": [(o["letter"], o["text"], "") for o in entry["options"]],
        "narration": "Pause here. Commit to an answer before the explanation.",
    })

    # 5 - silent pause
    scenes.append({
        "kind": "pause",
        "tag": tag,
        "system": entry["system"],
        "silent": True,
        "seconds": 3.5,
    })

    # 6 - reveal
    scenes.append({
        "kind": "reveal",
        "tag": tag,
        "system": entry["system"],
        "kicker": "THE ANSWER",
        "letter": correct["letter"],
        "sub": [correct["text"]],
        "narration": f"The answer is {correct['letter']}. {correct['text']}.",
    })

    # 7 - why the correct answer is correct
    scenes.append({
        "kind": "elim",
        "tag": tag,
        "system": entry["system"],
        "kicker": f"WHY {correct['letter']} IS RIGHT",
        "verdict": "right",
        "option": [correct["letter"], correct["text"]],
        "body": correct["why"],
        "narration": correct["why"],
    })

    # 8 - every distractor, with the signal that would have flipped it
    for opt in entry["options"]:
        if opt["correct"]:
            continue
        scenes.append({
            "kind": "elim",
            "tag": tag,
            "system": entry["system"],
            "kicker": f"WHY {opt['letter']} IS WRONG",
            "verdict": "wrong",
            "option": [opt["letter"], opt["text"]],
            "body": opt["why"],
            "bait": opt["would_make_right"],
            "narration": (
                f"{opt['why']} For {opt['letter']} to be the answer, you would need "
                f"this: {opt['would_make_right']}"
            ),
        })

    # 9 - the transferable rule
    scenes.append({
        "kind": "prose",
        "tag": tag,
        "system": entry["system"],
        "kicker": "THE RULE",
        "body": entry["rule"],
        "size": 42,
        "narration": entry["rule"],
    })

    return scenes


def outro_scene(next_entry: dict | None) -> dict:
    if next_entry:
        return {
            "kind": "outro",
            "tag": "NEXT",
            "system": next_entry["system"],
            "kicker": "NEXT",
            "big": next_entry["topic"].upper(),
            "sub": ["Subscribe to catch it.", "USMLE Step 1 · " + C.HANDLE],
            "narration": (
                f"Next: {next_entry['topic']}. Same format, same honesty about the wrong "
                f"answers. Subscribe so you don't miss it."
            ),
        }
    return {
        "kind": "outro",
        "tag": "NEXT",
        "system": "biostats",
        "kicker": "NEW SET",
        "big": "EVERY WEEK",
        "sub": ["Subscribe to catch it.", "USMLE Step 1 · " + C.HANDLE],
        "narration": "New questions every week. Subscribe so you don't miss the next set.",
    }


def build(entries: list[dict], next_entry: dict | None = None) -> list[dict]:
    """Full scene list for one video."""
    scenes = [intro_scene(len(entries), entries[0])]
    for i, entry in enumerate(entries, 1):
        scenes.extend(question_scenes(entry, i, len(entries)))
    scenes.append(outro_scene(next_entry))
    return scenes
