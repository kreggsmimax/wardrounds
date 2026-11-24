"""Preflight: can this channel actually publish today?

    python preflight.py

Prints a PASS/FAIL table and a single verdict. No side effects.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import config as C
from engine import facts

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

OK, BAD, WARN = "PASS", "FAIL", "WARN"
rows: list[tuple[str, str, str]] = []


def add(name: str, state: str, detail: str = "") -> None:
    rows.append((name, state, detail))


def check_binary(name: str, path: str) -> None:
    exe = path if Path(path).exists() else shutil.which(path)
    if not exe:
        add(name, BAD, "not found")
        return
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True,
                             timeout=15).stdout.splitlines()[0]
        add(name, OK, out.split("Copyright")[0].strip()[:52])
    except Exception as exc:  # noqa: BLE001
        add(name, BAD, str(exc)[:52])


def main() -> int:
    check_binary("ffmpeg", C.FFMPEG)
    check_binary("ffprobe", C.FFPROBE)

    for label, path in (("font regular", C.FONT_REGULAR), ("font bold", C.FONT_BOLD)):
        add(label, OK if Path(path).exists() else BAD, str(path)[-46:])

    try:
        import edge_tts  # noqa: F401
        add("edge-tts", OK, "importable")
    except ImportError:
        add("edge-tts", BAD, "pip install edge-tts")

    try:
        import PIL  # noqa: F401
        add("Pillow", OK, "importable")
    except ImportError:
        add("Pillow", BAD, "pip install Pillow")

    # ---- ledger -------------------------------------------------------
    try:
        everything = facts.load(approved_only=False)
    except facts.LedgerError as exc:
        add("ledger", BAD, str(exc)[:60])
        everything = []

    approved = [e for e in everything if e["review"]["status"] == "approved"]
    pending = len(everything) - len(approved)
    add("ledger approved", OK if approved else BAD, f"{len(approved)} entries")
    add("ledger pending", WARN if pending else OK, f"{pending} not yet reviewed")

    per_video = C.QUESTIONS_PER_VIDEO
    fresh = facts.fresh_count(approved)
    add("fresh inventory", OK if fresh >= per_video else BAD,
        f"{fresh} fresh, {per_video} needed per video")

    # how many daily videos before the ledger runs dry
    if per_video and fresh:
        add("days of runway", OK if fresh // per_video >= 7 else WARN,
            f"{fresh // per_video} day(s) at {per_video} questions/video")
    else:
        add("days of runway", BAD, "0")

    # ---- publish path --------------------------------------------------
    creds = [("YT_CLIENT_ID", os.getenv("YT_CLIENT_ID")),
             ("YT_CLIENT_SECRET", os.getenv("YT_CLIENT_SECRET")),
             ("YT_REFRESH_TOKEN", os.getenv("YT_REFRESH_TOKEN"))]
    missing = [n for n, v in creds if not v]
    add("youtube creds", OK if not missing else BAD,
        "all present" if not missing else f"missing {', '.join(missing)}")

    env_file = C.BASE_DIR / ".env"
    add(".env file", OK if env_file.exists() else WARN,
        "present" if env_file.exists() else "not created (Actions injects secrets)")

    # ---- repo ----------------------------------------------------------
    try:
        in_repo = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                                 capture_output=True, text=True, timeout=10)
        if in_repo.returncode == 0 and in_repo.stdout.strip() == "true":
            add("git repo", OK, "initialised")
        else:
            add("git repo", BAD, "not a git repo - Actions cannot run")
            return report()
    except Exception:  # noqa: BLE001
        add("git repo", BAD, "git not available")
        return report()

    remote = subprocess.run(["git", "remote"], capture_output=True, text=True, timeout=10)
    has_remote = bool(remote.stdout.strip())
    add("git remote", OK if has_remote else BAD,
        remote.stdout.strip().splitlines()[0] if has_remote else "no origin configured")

    # ---- workflow ------------------------------------------------------
    wf = C.BASE_DIR / ".github" / "workflows" / "daily.yml"
    add("workflow", OK if wf.exists() else BAD,
        "daily.yml present" if wf.exists() else "missing")

    # ---- last build ----------------------------------------------------
    latest = C.OUTPUT_DIR / "latest_video.json"
    if latest.exists():
        meta = json.loads(latest.read_text(encoding="utf-8"))
        add("last build", OK,
            f"{meta.get('minutes', 0):.1f} min, {meta.get('caption_cues', 0)} cues")
    else:
        add("last build", WARN, "no build yet")

    return report()


def report() -> int:
    width = max(len(r[0]) for r in rows) + 2
    print()
    print(f"{C.BRAND}  ·  PREFLIGHT")
    print("-" * 74)
    for name, state, detail in rows:
        mark = {"PASS": "[ok]  ", "WARN": "[warn]", "FAIL": "[FAIL]"}[state]
        print(f"{mark} {name:<{width}} {detail}")
    print("-" * 74)

    fails = [r for r in rows if r[1] == BAD]
    if fails:
        print(f"NOT READY - {len(fails)} blocker(s):")
        for name, _state, detail in fails:
            print(f"  · {name}: {detail}")
        return 1

    warns = [r for r in rows if r[1] == WARN]
    print("READY TO PUBLISH." + (f" {len(warns)} warning(s)." if warns else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
