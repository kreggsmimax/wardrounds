"""
Vertical Shorts cut. One question, 1080x1920, ~50 seconds.

Different job from the long-form: this is the discovery layer. It has to land the
surprise fast, so it drops the four-distractor elimination and keeps only the hook,
the stem, the pause and the reveal.
"""

from __future__ import annotations

import config as C

from engine import script as longform


def build(entry: dict) -> list[dict]:
    accent = longform._accent(entry)
    tag = longform._tag(entry)
    correct = longform._correct(entry)

    return [
        {
            "kind": "titlecard",
            "tag": tag,
            "system": entry["system"],
            "kicker": "USMLE STEP 1",
            "big": entry["topic"],
            "sub": [entry["hook"]],
            "narration": entry["hook"],
        },
        {
            "kind": "prose",
            "tag": tag,
            "system": entry["system"],
            "kicker": "THE VIGNETTE",
            "body": entry.get("short_vignette") or entry["vignette"],
            "size": 44,
            "narration": entry.get("short_vignette") or entry["vignette"],
        },
        {
            "kind": "options",
            "tag": tag,
            "system": entry["system"],
            "kicker": "PICK YOUR ANSWER",
            "options": [(o["letter"], o["text"], "") for o in entry["options"]],
            "narration": "Pause. Pick your answer.",
        },
        {
            "kind": "pause",
            "tag": tag,
            "system": entry["system"],
            "silent": True,
            "seconds": 2.5,
        },
        {
            "kind": "reveal",
            "tag": tag,
            "system": entry["system"],
            "kicker": "THE ANSWER",
            "letter": correct["letter"],
            "sub": [correct["text"]],
            "narration": f"The answer is {correct['letter']}. {correct['text']}.",
        },
        {
            "kind": "prose",
            "tag": tag,
            "system": entry["system"],
            "kicker": "THE RULE",
            "body": entry["rule"],
            "size": 52,
            "narration": entry["rule"],
        },
        {
            "kind": "outro",
            "tag": "FULL SET",
            "system": entry["system"],
            "kicker": "FULL BREAKDOWN",
            "big": "LINKED",
            "sub": ["Every wrong answer, explained.", C.HANDLE],
            "narration": (
                "The full breakdown, with all four wrong answers and what would have "
                "made each one correct, is on the channel."
            ),
        },
    ]
