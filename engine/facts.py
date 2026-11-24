"""
Verified fact ledger for the medical pipeline.

The design rule: the AI never authors a clinical fact. It receives facts from this
ledger and writes prose around them. Anything that must be true is stored here, once,
reviewed once, and versioned.

A question entry is the atomic unit. It becomes one long-form video segment or one
Short.

Validation is strict on purpose. A malformed entry should fail the build loudly
rather than reach a render.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "questions.json"
HISTORY = Path(__file__).resolve().parent.parent / "output" / "history" / "used_questions.json"

COOLDOWN_DAYS = 21

REQUIRED = {
    "id", "system", "topic", "difficulty", "hook", "vignette", "stem",
    "options", "rule", "sources", "review",
}
OPTION_REQUIRED = {"letter", "text", "correct", "why", "would_make_right"}
LETTERS = "ABCDE"
SYSTEMS = {"cardiology", "renal", "endocrine", "id", "heme", "pharm",
           "neuro", "biostats", "obgyn", "peds", "resp", "gi"}


class LedgerError(ValueError):
    """Raised when an entry would produce a medically unsafe video."""


def validate(entry: dict) -> None:
    """Raise LedgerError if the entry is incomplete or internally inconsistent."""
    qid = entry.get("id", "<no id>")
    missing = REQUIRED - set(entry)
    if missing:
        raise LedgerError(f"{qid}: missing keys {sorted(missing)}")

    if entry["system"] not in SYSTEMS:
        raise LedgerError(f"{qid}: unknown system {entry['system']!r}")
    if not 1 <= int(entry["difficulty"]) <= 5:
        raise LedgerError(f"{qid}: difficulty must be 1-5")

    opts = entry["options"]
    if not 3 <= len(opts) <= 5:
        raise LedgerError(f"{qid}: needs 3-5 options, got {len(opts)}")

    correct = [o for o in opts if o.get("correct")]
    if len(correct) != 1:
        raise LedgerError(f"{qid}: exactly one option must be correct, got {len(correct)}")

    for i, opt in enumerate(opts):
        omiss = OPTION_REQUIRED - set(opt)
        if omiss:
            raise LedgerError(f"{qid}[{opt.get('letter', i)}]: missing {sorted(omiss)}")
        if opt["letter"] != LETTERS[i]:
            raise LedgerError(f"{qid}: option letters must be sequential, got {opt['letter']} at {i}")
        # The elimination logic is the product. An empty "would_make_right" means the
        # video has a distractor it cannot explain, which is the whole point of the format.
        if len(opt["would_make_right"].strip()) < 15:
            raise LedgerError(f"{qid}[{opt['letter']}]: would_make_right too thin")

    if len(entry["rule"].strip()) < 20:
        raise LedgerError(f"{qid}: rule too thin")
    if not entry["sources"]:
        raise LedgerError(f"{qid}: needs at least one source")

    review = entry["review"]
    if review.get("status") not in {"approved", "pending", "rejected"}:
        raise LedgerError(f"{qid}: review.status must be approved|pending|rejected")
    if review.get("status") == "approved" and not review.get("by"):
        raise LedgerError(f"{qid}: approved entries need a reviewer")


def load(path: Path = DATA, approved_only: bool = True) -> list[dict]:
    """Load and validate the ledger. Returns approved entries only by default."""
    if not path.exists():
        raise LedgerError(f"no ledger at {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw["questions"] if isinstance(raw, dict) else raw

    out: list[dict] = []
    for entry in entries:
        validate(entry)
        if approved_only and entry["review"]["status"] != "approved":
            continue
        out.append(entry)

    if approved_only and not out:
        raise LedgerError("no approved entries - nothing is safe to render")
    return out


def pick(entries: list[dict], count: int, system: str | None = None,
         used_ids: set[str] | None = None, seed: int | None = None,
         strict: bool = False) -> list[dict]:
    """
    Choose questions for a video, avoiding recently used ids and spreading across
    systems so a single video never stacks three cardiology questions.

    strict=True refuses to fall back to used questions - the correct behaviour for a
    daily channel, where repeating yesterday's question is worse than not publishing.
    """
    rng = random.Random(seed)
    used_ids = used_ids or set()

    pool = [e for e in entries if e["id"] not in used_ids]
    if system:
        pool = [e for e in pool if e["system"] == system]

    if len(pool) < count:
        if strict:
            raise LedgerError(
                f"only {len(pool)} fresh approved question(s) available, {count} needed. "
                f"Add more entries to data/questions.json or lower QUESTIONS_PER_VIDEO."
            )
        pool = pool or list(entries)

    rng.shuffle(pool)
    chosen: list[dict] = []
    seen_systems: set[str] = set()

    for entry in pool:
        if len(chosen) == count:
            break
        if entry["system"] in seen_systems and len(chosen) < count - 1:
            continue
        chosen.append(entry)
        seen_systems.add(entry["system"])

    # backfill if the system-spread rule was too strict
    if len(chosen) < count:
        for entry in pool:
            if entry not in chosen:
                chosen.append(entry)
            if len(chosen) == count:
                break
    return chosen[:count]


def estimate_seconds(entry: dict) -> float:
    """
    Rough runtime for planning only. Real duration comes from the TTS word clocks.
    Based on observed rates from the sample render (~2.6 words/second at rate -5%).
    """
    words = len(entry["vignette"].split()) + len(entry["stem"].split())
    words += sum(len(o["why"].split()) + len(o["would_make_right"].split())
                 for o in entry["options"])
    words += len(entry["rule"].split())
    return words / 2.6 + 45.0  # + fixed beats: hook, pause card, reveal


# ------------------------------------------------------------------ rotation
def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def load_history(path: Path = HISTORY) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("used", [])
    except (json.JSONDecodeError, OSError):
        return []


def recent_ids(days: int = COOLDOWN_DAYS, path: Path = HISTORY) -> set[str]:
    """Question ids used inside the cooldown window - these must not be picked again."""
    from datetime import date, timedelta

    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return {row["id"] for row in load_history(path)
            if row.get("date", "") >= cutoff}


def record_used(entries: list[dict], path: Path = HISTORY) -> None:
    used = load_history(path)
    today = _today()
    known = {row["id"] for row in used if row.get("date") == today}
    for entry in entries:
        if entry["id"] not in known:
            used.append({"id": entry["id"], "date": today, "topic": entry["topic"]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"used": used}, indent=2, ensure_ascii=False),
                    encoding="utf-8")


def fresh_count(approved: list[dict], cooldown: int = COOLDOWN_DAYS) -> int:
    """How many approved questions are outside the cooldown window."""
    blocked = recent_ids(cooldown)
    return sum(1 for e in approved if e["id"] not in blocked)
