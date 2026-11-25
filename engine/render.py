"""Narration, captions and ffmpeg assembly."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import time
from pathlib import Path

import edge_tts

import config as C

ENDPOINTS = [
    "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1"
    "?TrustedClientToken=6A5AA1D4EAFF4E9FB37E23D68491D6F4",
    "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
    "?Ocp-Apim-Subscription-Key=6A5AA1D4EAFF4E9FB37E23D68491D6F4",
]


# ------------------------------------------------------------------ tts
def restore_punctuation(text: str, words: list[dict]) -> list[dict]:
    """WordBoundary events arrive unpunctuated; map source tokens back on."""
    tokens = text.split()
    if len(tokens) == len(words):
        for word, tok in zip(words, tokens):
            word["w"] = tok
        return words

    out: list[dict] = []
    j = 0
    for tok in tokens:
        want = "".join(ch for ch in tok.lower() if ch.isalnum())
        matched = False
        while j < len(words):
            have = "".join(ch for ch in words[j]["w"].lower() if ch.isalnum())
            if want and have and (want.startswith(have) or have.startswith(want)):
                out.append({"t": words[j]["t"], "d": words[j]["d"], "w": tok})
                j += 1
                matched = True
                break
            j += 1
        if not matched:
            prev = out[-1] if out else {"t": 0.0, "d": 0.0}
            out.append({"t": prev["t"] + prev["d"], "d": 0.0, "w": tok})
    return out


async def _tts(text: str, mp3_path: Path, words_path: Path) -> None:
    import edge_tts.communicate
    import edge_tts.constants

    last: Exception | None = None
    for attempt in range(1, 7):
        endpoint = ENDPOINTS[(attempt - 1) % len(ENDPOINTS)]
        edge_tts.constants.WSS_URL = endpoint
        edge_tts.communicate.WSS_URL = endpoint
        try:
            words: list[dict] = []
            with mp3_path.open("wb") as fh:
                comm = edge_tts.Communicate(text, C.VOICE, rate=C.RATE,
                                            boundary="WordBoundary")
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        fh.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        words.append({
                            "t": chunk["offset"] / 10_000_000,
                            "d": chunk["duration"] / 10_000_000,
                            "w": chunk["text"],
                        })
            if mp3_path.exists() and mp3_path.stat().st_size > 1000:
                words_path.write_text(json.dumps(restore_punctuation(text, words)),
                                      encoding="utf-8")
                return
            raise RuntimeError("empty audio")
        except Exception as exc:  # noqa: BLE001 - network flake, retry anything
            last = exc
            await asyncio.sleep(1.0 + attempt * 0.8)
    raise RuntimeError(f"TTS failed after 6 attempts: {last}")


def tts(text: str, cache_dir: Path) -> tuple[Path, list[dict]]:
    """Synthesise (cached) and return the mp3 path plus word timings."""
    key = hashlib.sha1(("v1" + C.VOICE + C.RATE + text).encode()).hexdigest()[:16]
    mp3 = cache_dir / f"{key}.mp3"
    words_file = cache_dir / f"{key}.words.json"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if (not mp3.exists() or mp3.stat().st_size < 1000
            or not words_file.exists() or words_file.stat().st_size <= 2):
        mp3.unlink(missing_ok=True)
        words_file.unlink(missing_ok=True)
        asyncio.run(_tts(text, mp3, words_file))

    words = json.loads(words_file.read_text(encoding="utf-8")) if words_file.exists() else []
    return mp3, words


# ------------------------------------------------------------------ captions
def build_cues(words: list[dict], offset: float = 0.0,
               max_words: int = C.CAP_MAX_WORDS,
               max_chars: int = C.CAP_MAX_CHARS) -> list[dict]:
    cues: list[dict] = []
    cur: list[dict] = []

    def flush() -> None:
        if not cur:
            return
        start = cur[0]["t"] + offset
        end = cur[-1]["t"] + cur[-1]["d"] + offset
        cues.append({"start": start, "end": max(end + 0.15, start + 0.55),
                     "words": [dict(w, t=w["t"] + offset) for w in cur]})
        cur.clear()

    for word in words:
        joined = " ".join(w["w"] for w in cur)
        if cur and (len(cur) >= max_words
                    or len(joined) + len(word["w"]) + 1 > max_chars):
            flush()
        cur.append(word)
        if word["w"].rstrip().endswith((".", "?", "!")) and len(cur) >= 4:
            flush()
    flush()

    for a, b in zip(cues, cues[1:]):
        if a["end"] > b["start"] - 0.02:
            a["end"] = max(a["start"] + 0.30, b["start"] - 0.02)
    return cues


def _srt_time(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _wrap(text: str, line_chars: int, sep: str = r"\N") -> str:
    """Split into two balanced lines, but never separate a short number from its word."""
    if len(text) <= line_chars:
        return text

    spaces = [i for i, ch in enumerate(text) if ch == " "]
    if not spaces:
        return text

    def orphans_number(i: int) -> bool:
        nxt = text[i + 1:].split(" ", 1)[0].strip(",.;:")
        return nxt.isdigit() and len(nxt) <= 2

    candidates = [i for i in spaces if not orphans_number(i)] or spaces
    cut = min(candidates, key=lambda i: abs(i - len(text) / 2))
    return text[:cut] + sep + text[cut + 1:]


def write_srt(cues: list[dict], path: Path, line_chars: int = C.CAP_LINE_CHARS) -> None:
    lines = []
    for i, cue in enumerate(cues, 1):
        text = _wrap(" ".join(w["w"] for w in cue["words"]), line_chars, sep="\n")
        lines.append(f"{i}\n{_srt_time(cue['start'])} --> {_srt_time(cue['end'])}\n{text}\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def _cue_split(texts: list[str], line_chars: int) -> int | None:
    """Pick the two-line break ONCE per cue, by word index.

    Computing this per-word (on the tagged string) is what made the captions jump:
    the override tags shift the character offsets, so the break landed somewhere
    different for every highlighted word.
    """
    total = len(" ".join(texts))
    if total <= line_chars or len(texts) < 2:
        return None
    half = total / 2
    acc, best, best_diff = 0, 1, 1e9
    for i in range(1, len(texts)):
        acc += len(texts[i - 1]) + 1
        diff = abs(acc - half)
        if diff < best_diff:
            best_diff, best = diff, i
    return best


def _compose(texts: list[str], active: int, split: int | None) -> str:
    def seg(lo: int, hi: int) -> str:
        out = []
        for j in range(lo, hi):
            tok = texts[j]
            if j == active:
                tok = r"{\c" + C.CAP_ACCENT_ASS + "}" + tok + r"{\c&HFFFFFF&}"
            out.append(tok)
        return " ".join(out)

    if split is None:
        return seg(0, len(texts))
    return seg(0, split) + r"\N" + seg(split, len(texts))


def write_ass(cues: list[dict], path: Path, W: int, H: int) -> None:
    vertical = H > W
    size = 54 if vertical else 42
    margin_v = 430 if vertical else 150
    margin_h = 70 if vertical else 120

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Segoe UI,{size},&H00FFFFFF,&H000000FF,&H00141418,&H6E000000,-1,0,0,0,100,100,0.3,0,3,9,0,2,{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for cue in cues:
        texts = [w["w"] for w in cue["words"]]
        if C.CAPTION_HIGHLIGHT:
            for i in range(len(texts)):
                start = cue["words"][i]["t"]
                end = (cue["words"][i + 1]["t"] if i + 1 < len(texts) else cue["end"])
                if end <= start:
                    continue
                events.append(
                    f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,"
                    f"{_compose(texts, i, None)}")
        else:
            events.append(
                f"Dialogue: 0,{_ass_time(cue['start'])},{_ass_time(cue['end'])},"
                f"Cap,,0,0,0,,{_compose(texts, -1, None)}")

    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ ffmpeg
def _run(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(args, check=True, cwd=str(cwd) if cwd else None)


def duration(path: Path) -> float:
    return float(subprocess.run(
        [C.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip())


def _silence(path: Path, seconds: float) -> None:
    _run([C.FFMPEG, "-y", "-v", "error", "-f", "lavfi",
          "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{seconds}",
          "-c:a", "aac", str(path)])


def _segment(png: Path, audio: Path, out: Path) -> None:
    _run([C.FFMPEG, "-y", "-v", "error",
          "-loop", "1", "-framerate", str(C.FPS), "-i", str(png), "-i", str(audio),
          "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
          "-af", f"apad=pad_dur={C.TAIL_PAD},aresample=44100",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-g", "60",
          "-threads", "2",
          "-r", str(C.FPS),
          "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
          "-shortest", str(out)])


def _segment_retry(png: Path, audio: Path, out: Path, attempts: int = 4) -> None:
    """ffmpeg occasionally dies with a native exception on Windows under memory
    pressure. The same command succeeds on retry, so retry instead of losing a
    30-minute CI run."""
    for attempt in range(1, attempts + 1):
        try:
            _segment(png, audio, out)
            return
        except subprocess.CalledProcessError:
            if attempt == attempts:
                raise
            print(f"      ffmpeg retry {attempt}/{attempts - 1} for {out.name}")
            time.sleep(1.5 * attempt)


# ------------------------------------------------------------------ render
def render(scenes: list[dict], name: str, out_dir: Path,
           W: int = C.VIDEO_WIDTH, H: int = C.VIDEO_HEIGHT,
           burn_captions: bool = True) -> dict:
    from engine.frames import Frame

    work = out_dir / "work" / name
    cache = out_dir / "work" / "audio"
    work.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    vertical = H > W
    cap_words = 7 if vertical else C.CAP_MAX_WORDS
    cap_chars = 42 if vertical else C.CAP_MAX_CHARS

    segs: list[Path] = []
    cues: list[dict] = []
    manifest: list[dict] = []
    cursor = 0.0
    total = len(scenes)

    for i, spec in enumerate(scenes):
        frame = Frame(spec, W, H)
        frame.draw(i, total)
        png = work / f"{i:02d}.png"
        frame.img.save(png)

        audio = work / f"{i:02d}.m4a"
        if spec.get("silent"):
            _silence(audio, spec.get("seconds", 3.5))
        else:
            mp3, words = tts(spec["narration"], cache)
            cues.extend(build_cues(words, cursor, cap_words, cap_chars))
            _run([C.FFMPEG, "-y", "-v", "error", "-i", str(mp3),
                  "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                  str(audio)])

        seg = work / f"{i:02d}.mp4"
        _segment_retry(png, audio, seg)
        segs.append(seg)

        secs = duration(seg)
        cursor += secs
        manifest.append({"index": i, "kind": spec["kind"],
                         "seconds": round(secs, 2), "beat": spec.get("kicker", "")})
        print(f"  [{i + 1:02d}/{total}] {spec['kind']:<9} {secs:6.2f}s  "
              f"{spec.get('kicker', '')[:38]}")

    write_srt(cues, out_dir / f"{name}.srt", 21 if vertical else C.CAP_LINE_CHARS)
    write_ass(cues, work / "captions.ass", W, H)

    lst = work / "concat.txt"
    lst.write_text("\n".join(f"file '{s.as_posix()}'" for s in segs), encoding="utf-8")
    joined = work / "joined.mp4"
    _run([C.FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0",
          "-i", str(lst), "-c", "copy", str(joined)])

    length = duration(joined)
    final = out_dir / f"{name}.mp4"
    vf = (f"fade=t=in:st=0:d=0.5,"
          f"fade=t=out:st={max(0.0, length - 0.7):.2f}:d=0.7")
    if burn_captions:
        vf += ",ass=captions.ass"

    _run([C.FFMPEG, "-y", "-v", "error", "-i", str(joined),
          "-vf", vf,
          "-af", (f"afade=t=in:st=0:d=0.35,"
                  f"afade=t=out:st={max(0.0, length - 0.8):.2f}:d=0.8,"
                  f"loudnorm=I=-16:TP=-1.5:LRA=11"),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
          "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)],
         cwd=work)

    return {"video": final, "duration": length, "scenes": manifest,
            "cues": len(cues), "srt": out_dir / f"{name}.srt"}
