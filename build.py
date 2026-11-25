"""Build one Ward Rounds video end to end.

    python build.py                    # 2 questions, default set
    python build.py --questions 1      # single-question deep dive
    python build.py --list             # show the ledger and review status
    python build.py --no-captions      # sidecar .srt only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

import config as C
from engine import facts, render, script, seo, shorts, verify

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def thumbnail(entry: dict, path) -> None:
    from engine.frames import Frame

    spec = {
        "kind": "titlecard",
        "tag": C.SYSTEM_LABEL.get(entry["system"], entry["system"].upper()),
        "system": entry["system"],
        "kicker": "USMLE STEP 1",
        "big": entry["topic"].upper(),
        "sub": [entry["hook"]],
    }
    frame = Frame(spec, 1280, 720)
    frame.draw(0, 1)
    frame.img.save(path, quality=92)


def main() -> int:
    ap = argparse.ArgumentParser(description=f"{C.BRAND} builder")
    ap.add_argument("--questions", type=int, default=C.QUESTIONS_PER_VIDEO)
    ap.add_argument("--system", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--no-captions", action="store_true",
                    help="disable burned-in subtitles (the .srt sidecar still ships)")
    ap.add_argument("--burn-captions", action="store_true",
                    help="force subtitles on (default)")
    ap.add_argument("--shorts", action="store_true",
                    help="also render a 9:16 Short from the first question")
    ap.add_argument("--cooldown", type=int, default=facts.COOLDOWN_DAYS,
                    help="days before a question may be reused")
    ap.add_argument("--fresh", action="store_true",
                    help="ignore the cooldown (only for testing)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    everything = facts.load(approved_only=False)

    if args.list:
        print(f"{'status':<9} {'id':<40} {'system':<12} topic")
        print("-" * 96)
        for e in everything:
            print(f"{e['review']['status']:<9} {e['id']:<40} "
                  f"{e['system']:<12} {e['topic']}")
        approved = sum(1 for e in everything if e["review"]["status"] == "approved")
        print(f"\n{approved} approved of {len(everything)}. "
              f"Pending entries are never rendered.")
        return 0

    print("=" * 78)
    print(f"  {C.BRAND}  ·  USMLE STEP 1 QUESTION SET")
    print("=" * 78)

    approved = [e for e in everything if e["review"]["status"] == "approved"]
    if not approved:
        print("no approved questions - nothing is safe to render")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    used = set() if args.fresh else facts.recent_ids(args.cooldown)
    fresh = facts.fresh_count(approved, args.cooldown) if not args.fresh else len(approved)

    print(f"\n[1/5] Inventory")
    print(f"      approved : {len(approved)}")
    print(f"      cooling  : {len(approved) - fresh} (used in the last {args.cooldown} days)")
    print(f"      fresh    : {fresh}")
    if fresh < args.questions:
        print(f"\n      Not enough fresh questions for a {args.questions}-question video.")
        if fresh > 0:
            print(f"      Run with --questions {fresh}, or add "
                  f"{args.questions - fresh} more approved entries to "
                  f"data/questions.json.")
        else:
            print(f"      Every approved question is inside the {args.cooldown}-day "
                  f"window. Add {args.questions} more approved entries to "
                  f"data/questions.json.")
        if not args.fresh:
            return 1

    chosen = facts.pick(approved, args.questions, system=args.system,
                        used_ids=used, seed=stamp, strict=not args.fresh)

    print(f"\n[1/5] Questions")
    for i, e in enumerate(chosen, 1):
        est = facts.estimate_seconds(e)
        print(f"      Q{i}  {e['id']}")
        print(f"          {e['topic']}  [{e['system']}]  ~{est:.0f}s estimated")

    remaining = [e for e in approved if e not in chosen]
    nxt = remaining[0] if remaining else None

    print(f"\n[2/5] Scenes")
    scenes = script.build(chosen, nxt)
    print(f"      {len(scenes)} scenes")

    print(f"\n[3/5] Verify")
    verify.require_clean(scenes, chosen)

    name = args.name or f"{C.BRAND.lower().replace(' ', '')}_{stamp}"
    out_dir = C.OUTPUT_DIR / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[4/5] Render")
    started = time.time()
    result = render.render(
        scenes, name, out_dir,
        burn_captions=args.burn_captions or (C.BURN_CAPTIONS and not args.no_captions))
    elapsed = time.time() - started

    seconds = result["duration"]
    if seconds > C.MAX_SECONDS:
        print(f"      WARNING: {seconds / 60:.1f} min exceeds the "
              f"{C.MAX_SECONDS / 60:.0f} min ceiling")

    print(f"\n[5/5] Metadata + thumbnail")
    title = seo.title(chosen)
    desc = seo.description(chosen, seconds)
    thumb = out_dir / f"{name}.jpg"
    thumbnail(chosen[0], thumb)

    short_info: dict = {}
    if args.shorts:
        print(f"      Shorts cut (9:16)")
        short_scenes = shorts.build(chosen[0])
        short_issues = verify.check_scenes(
            short_scenes, chosen[0],
            vignette=chosen[0].get("short_vignette"), include_options=False)
        if short_issues:
            raise SystemExit("SHORT VERIFICATION FAILED:\n  " + "\n  ".join(short_issues))
        short_info = render.render(
            short_scenes, f"{name}_short", out_dir,
            W=C.SHORT_WIDTH, H=C.SHORT_HEIGHT,
            burn_captions=args.burn_captions or (C.BURN_CAPTIONS and not args.no_captions))
        print(f"      short: {short_info['duration']:.0f}s")

    facts.record_used(chosen)

    payload = {
        "brand": C.BRAND,
        "handle": C.HANDLE,
        "timestamp": stamp,
        "video_path": str(result["video"]),
        "short_path": str(short_info["video"]) if short_info else "",
        "thumbnail_path": str(thumb),
        "srt_path": str(result["srt"]),
        "title": title,
        "description": desc,
        "tags": seo.tags(chosen),
        "hashtags": seo.hashtags(chosen),
        "duration_seconds": round(seconds, 2),
        "minutes": round(seconds / 60, 2),
        "render_minutes": round(elapsed / 60, 2),
        "scenes": result["scenes"],
        "caption_cues": result["cues"],
        "questions": [
            {"id": e["id"], "system": e["system"], "topic": e["topic"],
             "correct": next(o["letter"] for o in e["options"] if o["correct"])}
            for e in chosen
        ],
        "privacy": "private",
    }
    (C.OUTPUT_DIR / "latest_video.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / f"{name}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (C.OUTPUT_DIR / "latest.txt").write_text(str(result["video"]), encoding="utf-8")

    print("\n" + "=" * 78)
    print("  COMPLETE")
    print("=" * 78)
    print(f"  Video     : {result['video']}")
    print(f"  Duration  : {seconds:.0f}s  ({seconds / 60:.1f} min)")
    print(f"  Render    : {elapsed / 60:.1f} min")
    print(f"  Captions  : {result['cues']} cues")
    print(f"  Thumbnail : {thumb.name}")
    print(f"  Title     : {title}")
    if short_info:
        print(f"  Short     : {short_info['video'].name} "
              f"({short_info['duration']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
