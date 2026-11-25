"""Verify captions: single line, and the line never moves.

Colour changes are expected (the active word is tinted), so this measures the
caption's geometry - how many lines it occupies and where they sit - not raw pixels.
"""

import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

VIDEO = Path(sys.argv[1])
ASS = Path(sys.argv[2])
FFMPEG = r"C:\ffmpeg\bin\ffmpeg.exe"

ASS_RE = re.compile(r"Dialogue: 0,(\d+):(\d+):(\d+)\.(\d+),"
                    r"(\d+):(\d+):(\d+)\.(\d+),")


def secs(h, m, s, cs):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100


cues = []
for line in ASS.read_text(encoding="utf-8").splitlines():
    m = ASS_RE.search(line)
    if m:
        start = secs(*m.groups()[:4])
        end = secs(*m.groups()[4:])
        if end - start > 1.4:
            cues.append((start, end))

print(f"long cues: {len(cues)}")


def geometry(png: Path):
    """Return (line_count, top, bottom) for the caption band only."""
    img = np.asarray(Image.open(png).convert("L"), dtype=np.int16)
    h = img.shape[0]
    # captions are bottom-anchored at MarginV; this band excludes the wordmark below
    top_row, bottom_row = h - 222, h - 142
    strip = img[top_row:bottom_row, :]
    bright = strip.max(axis=1) > 110
    rows = np.flatnonzero(bright)
    if len(rows) == 0:
        return 0, 0, 0
    groups, prev = 1, rows[0]
    for r in rows[1:]:
        if r - prev > 6:
            groups += 1
        prev = r
    return groups, int(rows[0]) + top_row, int(rows[-1]) + top_row


tmp = Path("build/verify")
tmp.mkdir(parents=True, exist_ok=True)
picks = cues[4:9] if len(cues) > 10 else cues[:5]

fail = 0
for idx, (start, _end) in enumerate(picks):
    info = []
    for j, t in enumerate([start + 0.2, start + 0.7, start + 1.1]):
        out = tmp / f"c{idx}_{j}.png"
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{t:.2f}",
                        "-i", str(VIDEO), "-frames:v", "1", str(out)], check=True)
        info.append(geometry(out))

    lines = {i[0] for i in info}
    tops = {i[1] for i in info}
    bots = {i[2] for i in info}
    still = len(tops) == 1 and len(bots) == 1
    single = lines == {1}
    ok = still and single
    fail += 0 if ok else 1
    print(f"  cue {idx}: lines={sorted(lines)} top={sorted(tops)} "
          f"bottom={sorted(bots)}  {'OK' if ok else 'FAIL'}")

print("\nPASS - single line, no movement" if fail == 0 else f"\nFAIL - {fail} cue(s)")
sys.exit(0 if fail == 0 else 1)
