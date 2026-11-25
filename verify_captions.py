"""Verify captions stay put: sample three frames inside several cues and diff them."""
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

VIDEO = Path(sys.argv[1]) if len(sys.argv) > 1 else None
ASS = Path(sys.argv[2]) if len(sys.argv) > 2 else None

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
        if end - start > 1.6:
            cues.append((start, end))

picks = cues[3:3 + 5] if len(cues) > 8 else cues[:5]
print(f"long cues available: {len(cues)}   sampling {len(picks)}\n")

tmp = Path("build/verify")
tmp.mkdir(parents=True, exist_ok=True)
worst = 0.0
for idx, (start, _end) in enumerate(picks):
    stamps = [start + 0.25, start + 0.85, start + 1.45]
    frames = []
    for j, t in enumerate(stamps):
        out = tmp / f"v{idx}_{j}.png"
        subprocess.run([r"C:\ffmpeg\bin\ffmpeg.exe", "-y", "-v", "error",
                        "-ss", f"{t:.2f}", "-i", str(VIDEO), "-frames:v", "1", str(out)],
                       check=True)
        frames.append(np.asarray(Image.open(out).convert("L"), dtype=np.int16))
    h = frames[0].shape[0]
    strip = [f[int(h * 0.70):, :] for f in frames]
    d01 = float(np.abs(strip[0] - strip[1]).mean())
    d12 = float(np.abs(strip[1] - strip[2]).mean())
    worst = max(worst, d01, d12)
    state = "STILL" if max(d01, d12) < 2.0 else "MOVED"
    print(f"  cue {idx}: {stamps[0]:6.2f}s  diff {d01:.2f} / {d12:.2f}   {state}")

print(f"\nworst caption-region diff across samples: {worst:.2f}")
print("PASS - captions are static" if worst < 2.0 else "FAIL - captions still move")
