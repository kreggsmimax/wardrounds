"""
Pollinations-backed question generation.

The pipeline can run two ways:

  1. Curated  - humans write entries in data/questions.json (safe, slow)
  2. Automated - this module drafts a Step 1 question, runs a second model as a
                 fact-checker, and only promotes it to the ledger if both passes agree

Automated mode is how the daily schedule sustains itself. It is still a model, so a
human spot-check of the first weeks is the difference between a channel and a liability.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from pathlib import Path

import requests

import config as C
from engine import facts

API = "https://gen.pollinations.ai/v1/chat/completions"
KEY = os.getenv("POLLINATIONS_API_KEY", "")
MODEL = os.getenv("AI_MODEL", "openai/gpt-5.4-nano")
FALLBACK = os.getenv("AI_FALLBACK_MODEL", "openai/gpt-4.1-nano")

LEDGER = Path(__file__).resolve().parent.parent / "data" / "questions.json"

DRAFT_SYSTEM = (
    "You are a senior USMLE Step 1 question writer with a pharmacology and "
    "pathophysiology background. You write board-style vignettes that test mechanism, "
    "not trivia. You never invent lab values that contradict the diagnosis, never give "
    "drug doses, and never reproduce copyrighted question-bank material."
)

REVIEW_SYSTEM = (
    "You are a USMLE Step 1 content editor doing a blocking review. You only reject a "
    "question if it contains a fatal defect. Fatal means one of:\n"
    "  - the marked answer is not the single best answer\n"
    "  - another option is equally or more correct\n"
    "  - a stated fact or mechanism is wrong\n"
    "  - the labs, vitals or exam findings are internally impossible\n"
    "  - an explanation tells the student something medically false\n"
    "Style, brevity, missing nuance, imperfect realism and imperfect distractors are "
    "NOT fatal. Do not reject for those. A question you would merely improve is an accept."
)

SCHEMA = """{
  "system": one of ["cardiology","renal","endocrine","id","heme","pharm","neuro","biostats","obgyn","peds","resp","gi"],
  "topic": "short topic name, title case",
  "difficulty": 1-5 integer,
  "hook": "one sentence that names the trap. max 20 words.",
  "key_finding": "the single decisive finding, max 8 words, e.g. 'Carotid upstroke: delayed and low amplitude'",
  "vignette": "USMLE-style stem, 55-110 words. Age, sex, presentation, then specific vitals and labs as numbers.",
  "short_vignette": "condensed version for a 45s vertical cut, max 32 words",
  "stem": "the question, ends with a question mark",
  "options": [ exactly 5 objects {"letter":"A","text":"...","correct":bool,"why":"1-2 sentences","would_make_right":"the specific vignette change that would make THIS option correct"} ],
  "rule": "one transferable sentence a student can reuse on other questions",
  "sources": ["First Aid for the USMLE Step 1 - <section>", "optional guideline name"]
}"""


# ------------------------------------------------------------------ transport
def _post(payload: dict, timeout: int = 120) -> dict:
    if not KEY:
        raise RuntimeError("POLLINATIONS_API_KEY is not set")
    r = requests.post(
        API,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def _chat(system: str, user: str, model: str, seed: int, temperature: float = 0.95) -> str:
    data = _post({
        "model": model,
        "seed": seed,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    })
    return data["choices"][0]["message"]["content"]


def _json_object(text: str) -> dict:
    """Pull the first balanced JSON object out of a model response."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in response")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced JSON in response")


def _models() -> list[str]:
    out = [MODEL]
    if FALLBACK and FALLBACK != MODEL:
        out.append(FALLBACK)
    return out


# ------------------------------------------------------------------ generation
def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "question"


def generate_one(system: str, avoid_topics: list[str], seed: int) -> dict:
    avoid = ""
    if avoid_topics:
        avoid = ("Do not reuse these topics: " + "; ".join(avoid_topics[:40]) + ".\n")

    prompt = (
        f"Write ONE USMLE Step 1 question for the {system} system.\n"
        f"{avoid}"
        "Requirements:\n"
        "- Exactly one option is correct.\n"
        "- Every 'would_make_right' must name a concrete change to the vignette, not a platitude.\n"
        "- The 'why' for wrong options must explain the misunderstanding they are testing.\n"
        "- Use realistic values. Do not use drug doses.\n"
        "- The hook is a spoken sentence the viewer hears first. No 'Trap:' prefix, no labels.\n"
        f"- Return ONLY a JSON object with exactly these keys:\n{SCHEMA}\n"
    )

    last: Exception | None = None
    for model in _models():
        for attempt in range(3):
            try:
                raw = _chat(DRAFT_SYSTEM, prompt, model, seed + attempt * 137)
                entry = _json_object(raw)
                entry = _normalise(entry, system)
                facts.validate(entry)
                return entry
            except Exception as exc:  # noqa: BLE001 - model boundary
                last = exc
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"generation failed for {system}: {last}")


def _normalise(entry: dict, system: str) -> dict:
    """Fill defaults, force letters A-E, and build a deterministic id."""
    entry.setdefault("system", system)
    entry.setdefault("difficulty", 2)
    entry.setdefault("sources", ["First Aid for the USMLE Step 1"])
    entry.setdefault("short_vignette", entry.get("vignette", ""))

    letters = "ABCDE"
    opts = list(entry.get("options", []))[:5]
    for i, opt in enumerate(opts):
        opt["letter"] = letters[i]
        opt["correct"] = bool(opt.get("correct"))
    entry["options"] = opts

    if not any(o["correct"] for o in opts) and opts:
        opts[0]["correct"] = True

    entry["id"] = f"{_slug(entry.get('system', system))}-{_slug(entry.get('topic', 'topic'))}-{_slug(entry.get('hook', ''))[:18]}"
    entry["review"] = {
        "status": "pending",
        "by": "",
        "date": "",
        "note": "drafted by model, awaiting review",
    }
    return entry


# ------------------------------------------------------------------ review
def review(entry: dict) -> tuple[bool, list[str]]:
    """Second model pass. Returns (ok, issues)."""
    prompt = (
        "Review this USMLE Step 1 question.\n\n"
        f"{json.dumps(entry, ensure_ascii=False, indent=2)}\n\n"
        "Reject ONLY for a fatal defect:\n"
        "1. the marked correct answer is wrong or not the single best answer\n"
        "2. another option is equally or more correct\n"
        "3. a stated mechanism, drug effect or association is factually wrong\n"
        "4. the labs/vitals/exam findings are internally impossible\n"
        "5. an explanation asserts something medically false\n\n"
        'Return ONLY JSON: {"ok": true|false, "issues": ["..."]}'
    )
    for model in _models():
        for attempt in range(2):
            try:
                raw = _chat(REVIEW_SYSTEM, prompt, model, 7 + attempt * 91, temperature=0.2)
                out = _json_object(raw)
                return bool(out.get("ok")), [str(i) for i in out.get("issues", [])]
            except Exception:  # noqa: BLE001
                time.sleep(1.2 * (attempt + 1))
    # if the reviewer is unreachable, do not silently approve
    return False, ["reviewer unavailable"]


# ------------------------------------------------------------------ ledger
def _load_ledger() -> dict:
    if not LEDGER.exists():
        return {"version": 1, "questions": []}
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def _save_ledger(data: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def top_up(need: int, systems: list[str] | None = None,
           max_attempts: int = 12, verbose: bool = True) -> int:
    """Draft questions until `need` are approved, and append them to the ledger."""
    if need <= 0:
        return 0

    data = _load_ledger()
    existing = data.get("questions", [])
    used_topics = [q.get("topic", "") for q in existing]
    used_ids = {q.get("id") for q in existing}
    systems = systems or [s for s in C.SYSTEM_ACCENT if s != "biostats"]

    added = 0
    attempts = 0
    rng = random.Random()
    while added < need and attempts < max_attempts:
        attempts += 1
        system = systems[attempts % len(systems)]
        try:
            entry = generate_one(system, used_topics, seed=rng.randint(1, 10_000))
        except Exception as exc:  # noqa: BLE001
            if verbose:
                print(f"      draft failed ({system}): {str(exc)[:90]}")
            continue

        ok, issues = review(entry)
        if not ok:
            if verbose:
                print(f"      rejected by reviewer: {entry['topic']} - {'; '.join(issues)[:100]}")
            used_topics.append(entry["topic"])
            continue

        if entry["id"] in used_ids:
            entry["id"] = f"{entry['id']}-{attempts}"

        entry["review"] = {
            "status": "approved",
            "by": "auto-reviewer",
            "date": time.strftime("%Y-%m-%d"),
            "note": "drafted and passed the second-model review; spot-check recommended",
        }
        existing.append(entry)
        used_topics.append(entry["topic"])
        used_ids.add(entry["id"])
        added += 1
        if verbose:
            print(f"      + approved: {entry['topic']} [{entry['system']}]")

    if added:
        data["questions"] = existing
        _save_ledger(data)
    return added
