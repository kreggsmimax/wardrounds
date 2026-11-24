"""Title, description, tags for the uploader."""

from __future__ import annotations

import config as C


def _systems(entries: list[dict]) -> list[str]:
    seen, out = set(), []
    for e in entries:
        if e["system"] not in seen:
            seen.add(e["system"])
            out.append(C.SYSTEM_LABEL.get(e["system"], e["system"].title()))
    return out


def _trim(text: str, limit: int) -> str:
    text = text.strip().rstrip(".")
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def title(entries: list[dict]) -> str:
    systems = _systems(entries)
    label = systems[0].title()
    if len(entries) == 1:
        t = f"USMLE Step 1 {label}: {_trim(entries[0]['hook'], 62)}"
    else:
        t = (f"USMLE Step 1: {_trim(entries[0]['hook'], 58)} "
             f"— {len(entries)} Questions")
    return t[:100]


def description(entries: list[dict], duration: float) -> str:
    lines = [
        f"{len(entries)} Step 1 questions, full elimination. "
        f"Every distractor explained, plus the exact vignette change that would "
        f"have made it correct.",
        "",
        C.DISCLAIMER,
        "",
        "CHAPTERS",
    ]
    minute = 0
    for i, e in enumerate(entries, 1):
        lines.append(f"{minute:02d}:00  Q{i} · {e['topic']}")
        minute += max(1, round(duration / 60 / len(entries)))

    lines += ["", "SOURCES"]
    for e in entries:
        for s in e["sources"]:
            lines.append(f"· {s}")

    lines += [
        "",
        "Also relevant for: FMGE, NEET-PG, INI-CET, PLAB.",
        "",
        f"{C.BRAND} · {C.HANDLE}",
        "Read the stem. Beat the test.",
    ]
    return "\n".join(lines)[:4900]


def tags(entries: list[dict]) -> list[str]:
    base = ["usmle", "usmle step 1", "step 1", "medical education",
            "med school", "question bank", "medical student", "vignette"]
    for e in entries:
        base.append(e["topic"].lower())
        base.append(C.SYSTEM_LABEL.get(e["system"], e["system"]).lower())
    seen, out = set(), []
    for t in base:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:30]


def hashtags(entries: list[dict]) -> str:
    return " ".join(["#usmle", "#step1", "#medschool", "#medicaleducation",
                     f"#{entries[0]['system']}"])
