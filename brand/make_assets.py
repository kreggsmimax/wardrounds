"""
Channel brand assets for WARD ROUNDS.

Rendered with Pillow rather than an image model so the wordmark is pixel-exact and
matches the video palette (#0E1116 background, #F5A524 accent).

    python brand/make_assets.py

Produces:
    brand/avatar_1024.png        channel profile picture (upload manually in Studio)
    brand/banner_2560x1440.png   channel banner (safe area respected)
    brand/banner_preview.png     what viewers actually see on desktop
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
FONT_DIR = Path(r"C:\Windows\Fonts")

BG = (14, 17, 22)
TEXT = (240, 243, 247)
MUTED = (138, 148, 163)
AMBER = (245, 165, 36)
FAINT = (60, 68, 80)


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def background(w: int, h: int, glow: float = 0.16) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w * 0.5, h * 0.5
    d = np.sqrt(((xx - cx) / (w * 0.85)) ** 2 + ((yy - cy) / (h * 0.85)) ** 2)
    g = np.clip(1.0 - d, 0.0, 1.0) ** 2.2
    img = np.array(BG, dtype=np.float32)[None, None, :]
    img = img + g[:, :, None] * np.array(AMBER, dtype=np.float32) * glow
    img *= np.clip(1.0 - 0.55 * np.clip(d, 0, 1.7) ** 1.5, 0, 1)[:, :, None]
    img += np.random.default_rng(11).normal(0, 1.8, (h, w, 1))
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def ecg_points(x0: float, x1: float, y: float, beats: int, amp: float) -> list[tuple[float, float]]:
    """Stylised rhythm strip: flat baseline with periodic QRS complexes."""
    pts: list[tuple[float, float]] = []
    span = (x1 - x0) / beats
    for b in range(beats):
        bx = x0 + b * span
        pts += [
            (bx, y),
            (bx + span * 0.16, y),
            (bx + span * 0.20, y - amp * 0.18),
            (bx + span * 0.25, y + amp * 0.22),
            (bx + span * 0.29, y - amp),
            (bx + span * 0.33, y + amp * 0.38),
            (bx + span * 0.37, y - amp * 0.10),
            (bx + span * 0.42, y),
            (bx + span * 0.55, y - amp * 0.22),
            (bx + span * 0.68, y),
            (bx + span, y),
        ]
    return pts


def draw_tracked(draw: ImageDraw.ImageDraw, xy, text: str, f, fill, tracking: float):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill, anchor="lm")
        x += draw.textlength(ch, font=f) + tracking
    return x - tracking


def avatar(size: int = 1024) -> Image.Image:
    img = background(size, size, glow=0.20)
    d = ImageDraw.Draw(img)

    # thin ring so the monogram reads as a badge at 48px
    pad = size * 0.085
    d.ellipse([pad, pad, size - pad, size - pad], outline=FAINT, width=max(2, size // 340))

    f = font(int(size * 0.36))
    d.text((size / 2, size * 0.45), "WR", font=f, fill=TEXT, anchor="mm")

    # amber rhythm strip clearly below the letters
    pts = ecg_points(size * 0.26, size * 0.74, size * 0.705, beats=3, amp=size * 0.036)
    d.line(pts, fill=AMBER, width=max(3, size // 200), joint="curve")
    return img


def banner(w: int = 2560, h: int = 1440) -> Image.Image:
    img = background(w, h, glow=0.14)
    d = ImageDraw.Draw(img)

    # YouTube safe area: 1546 x 423, centred
    safe_w, safe_h = 1546, 423
    left = (w - safe_w) // 2
    top = (h - safe_h) // 2
    right, bottom = left + safe_w, top + safe_h

    # rhythm strip across the safe area, below the lockup
    pts = ecg_points(left + 40, right - 40, top + safe_h * 0.895, beats=7, amp=h * 0.048)
    d.line(pts, fill=AMBER, width=max(3, h // 320), joint="curve")

    # kicker
    kf = font(int(h * 0.026))
    kicker = "USMLE STEP 1  ·  QUESTION BY QUESTION"
    kw = sum(d.textlength(c, font=kf) for c in kicker) + h * 0.006 * (len(kicker) - 1)
    draw_tracked(d, ((w - kw) / 2, top + safe_h * 0.09), kicker, kf, MUTED, h * 0.006)

    # wordmark
    wf = font(int(h * 0.112))
    d.text((w / 2, top + safe_h * 0.36), "WARD ROUNDS", font=wf, fill=TEXT, anchor="mm")

    # tagline, above the rhythm strip
    tf = font(int(h * 0.032), bold=False)
    d.text((w / 2, top + safe_h * 0.615), "Every wrong answer, explained.",
           font=tf, fill=AMBER, anchor="mm")

    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    a = avatar()
    a.save(OUT / "avatar_1024.png")

    b = banner()
    b.save(OUT / "banner_2560x1440.png")

    # what a desktop viewer actually sees (1546 x 423 crop)
    safe = b.crop(((2560 - 1546) // 2, (1440 - 423) // 2,
                   (2560 + 1546) // 2, (1440 + 423) // 2))
    safe.save(OUT / "banner_preview.png")

    for name in ("avatar_1024.png", "banner_2560x1440.png", "banner_preview.png"):
        p = OUT / name
        print(f"  {name:26} {p.stat().st_size // 1024} KB  "
              f"{Image.open(p).size}")


if __name__ == "__main__":
    main()
