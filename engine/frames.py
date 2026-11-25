"""
Pillow scene renderer. One dict in, one 1080p frame out.

Derived from the tested sample renderer in ../../video/render_sample.py, extended with
two layouts the ledger needs: `prose` (vignette / stem text) and `elim` (why this option
is wrong, plus what would have made it right).
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config as C

_font_cache: dict[tuple[bool, int], ImageFont.FreeTypeFont] = {}


def F(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (bold, size)
    if key not in _font_cache:
        path = C.FONT_BOLD if bold else C.FONT_REGULAR
        _font_cache[key] = ImageFont.truetype(str(path), size)
    return _font_cache[key]


class Frame:
    def __init__(self, spec: dict, W: int = C.VIDEO_WIDTH, H: int = C.VIDEO_HEIGHT):
        self.spec = spec
        self.W, self.H = W, H
        self.base = min(W, H) * (1.30 if H > W else 1.0)
        self.margin = int(W * 0.085)
        self.accent = spec.get("accent_rgb") or C.SYSTEM_ACCENT.get(
            spec.get("system", "biostats"), C.MUTED)
        self.img = self._background()
        self.d = ImageDraw.Draw(self.img)
        self.maxw = W - 2 * self.margin

    # ---------------------------------------------------------------- base
    def fs(self, n: float) -> int:
        return max(8, int(n * self.base / 1080))

    def _background(self) -> Image.Image:
        W, H = self.W, self.H
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        cx, cy = W * 0.5, H * 0.38
        d = np.sqrt(((xx - cx) / (W * 0.78)) ** 2 + ((yy - cy) / (H * 0.78)) ** 2)
        glow = np.clip(1.0 - d, 0.0, 1.0) ** 2.4

        img = np.array(C.BG, dtype=np.float32)[None, None, :]
        img = img + glow[:, :, None] * np.array(self.accent, dtype=np.float32) * 0.14
        img *= np.clip(1.0 - 0.60 * np.clip(d, 0.0, 1.7) ** 1.6, 0.0, 1.0)[:, :, None]
        img += np.random.default_rng(7).normal(0.0, 2.0, (H, W, 1))
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))

    # ---------------------------------------------------------------- text
    def width(self, text: str, font) -> float:
        return self.d.textlength(text, font=font)

    def wrap(self, text: str, font, maxw: float | None = None) -> list[str]:
        maxw = maxw or self.maxw
        out: list[str] = []
        for para in str(text).split("\n"):
            line = ""
            for word in para.split():
                trial = f"{line} {word}".strip()
                if self.width(trial, font) <= maxw or not line:
                    line = trial
                else:
                    out.append(line)
                    line = word
            out.append(line)
        return out

    def fit(self, text: str, bold: bool, maxw: float, start: int, floor: int):
        size = start
        while size > floor:
            f = F(self.fs(size), bold)
            if self.width(text, f) <= maxw:
                return f
            size -= 4
        return F(self.fs(floor), bold)

    def tag(self, label: str) -> None:
        y = self.margin * 0.86
        f = F(self.fs(21), True)
        tracking = self.fs(4.5)
        total = sum(self.width(c, f) for c in label) + tracking * (len(label) - 1)
        x = self.margin
        for ch in label:
            self.d.text((x, y), ch, font=f, fill=self.accent, anchor="lm")
            x += self.width(ch, f) + tracking
        self.d.rectangle([self.margin, y + self.fs(26),
                          self.margin + total * 0.30, y + self.fs(29)], fill=self.accent)

    def wordmark(self, idx: int, total: int) -> None:
        f = F(self.fs(19), True)
        if self.H > self.W:
            # vertical: the bottom third is covered by the Shorts UI
            self.d.text((self.W - self.margin, self.margin * 0.86),
                        f"{C.BRAND} · {C.HANDLE}", font=f, fill=C.FAINT, anchor="rm")
            return

        y = self.H - self.margin * 0.80
        self.d.text((self.margin, y), f"{C.BRAND}  ·  {C.HANDLE}", font=f,
                    fill=C.FAINT, anchor="lm")
        bar_w = self.W - 2 * self.margin
        bar_y = y + self.fs(22)
        self.d.rectangle([self.margin, bar_y, self.margin + bar_w, bar_y + 2], fill=(34, 39, 47))
        done = bar_w * (idx + 1) / max(1, total)
        self.d.rectangle([self.margin, bar_y, self.margin + done, bar_y + 2], fill=self.accent)

    def kicker(self, text: str, color=None, y: float | None = None) -> None:
        """Letter-spaced label. Sits on the tag baseline, or below it when vertical."""
        f = F(self.fs(24), True)
        tracking = self.fs(7)
        text = text.upper()
        w = sum(self.width(c, f) for c in text) + tracking * max(0, len(text) - 1)
        x = (self.W - w) / 2
        if y is None:
            y = (self.margin * 0.86 + self.fs(78)) if self.H > self.W else self.margin * 0.86
        for ch in text:
            self.d.text((x, y), ch, font=f, fill=color or C.MUTED, anchor="lm")
            x += self.width(ch, f) + tracking

    def body_width(self) -> float:
        """Narrower measure than the full frame - long lines are hard to track."""
        return min(self.maxw, self.fs(1280))

    def stack(self, items: list[dict], center_y: float) -> None:
        prepared = []
        for it in items:
            f = it.get("font") or F(self.fs(it.get("size", 44)), it.get("bold", False))
            for line in self.wrap(it["text"], f):
                prepared.append((line, f, it.get("color", C.TEXT), it.get("gap", 0.30)))
        heights = []
        for _line, f, _c, gap in prepared:
            asc, desc = f.getmetrics()
            heights.append(asc + desc + self.fs(gap))
        y = center_y - sum(heights) / 2
        for (line, f, color, _gap), h in zip(prepared, heights):
            self.d.text((self.W / 2, y), line, font=f, fill=color, anchor="ma")
            y += h

    # ---------------------------------------------------------------- layouts
    def draw(self, idx: int, total: int) -> None:
        s = self.spec
        self.tag(s.get("tag", ""))
        kind = s["kind"]

        if kind in ("titlecard", "statement"):
            items = []
            if s.get("kicker"):
                items.append({"text": s["kicker"], "size": 24, "bold": True,
                              "color": self.accent, "gap": 1.10})
            big_font = self.fit(s.get("big", ""), True, self.maxw, start=132, floor=48)
            items.append({"text": s.get("big", ""), "font": big_font,
                          "bold": True, "gap": 0.40})
            for line in s.get("sub", []):
                items.append({"text": line, "size": 42, "color": C.MUTED, "gap": 0.28})
            self.stack(items, self.H * 0.52)

        elif kind == "prose":
            self.kicker(s.get("kicker", ""))
            size = s.get("size", 34)
            avail = self.H - 2 * self.margin - self.fs(120) - (self.fs(120) if self.H > self.W else 0)
            while True:
                font = F(self.fs(size), False)
                lines = self.wrap(s["body"], font, self.body_width())
                asc, desc = font.getmetrics()
                lh = (asc + desc) * 1.38
                if lh * len(lines) <= avail or size <= 14:
                    break
                size -= 2
            y = (self.H - lh * len(lines)) / 2
            for line in lines:
                self.d.text((self.W / 2, y), line, font=font, fill=C.TEXT, anchor="ma")
                y += lh

        elif kind == "options":
            self.kicker(s.get("kicker", "PICK YOUR ANSWER"))
            opts = s["options"]
            n = len(opts)
            card_h = min(self.fs(104), int((self.H * 0.56) / n))
            gap = self.fs(12)
            block = n * card_h + (n - 1) * gap
            top = self.H * 0.54 - block / 2
            for i, (letter, text, state) in enumerate(opts):
                y0 = top + i * (card_h + gap)
                hi = state == "correct"
                self.d.rounded_rectangle(
                    [self.margin, y0, self.W - self.margin, y0 + card_h],
                    radius=self.fs(12),
                    fill=(26, 44, 36) if hi else (22, 26, 33),
                    outline=C.GREEN if hi else (40, 46, 56),
                    width=3 if hi else 2)
                self.d.text((self.margin + self.fs(30), y0 + card_h / 2), letter,
                            font=F(self.fs(34), True), fill=self.accent, anchor="lm")
                self.d.text((self.margin + self.fs(88), y0 + card_h / 2), text,
                            font=F(self.fs(34), False),
                            fill=C.TEXT if hi else (200, 206, 216), anchor="lm")

        elif kind == "reveal":
            items = [{"text": s.get("kicker", "THE ANSWER"), "size": 24, "bold": True,
                      "color": C.GREEN, "gap": 1.0},
                     {"text": s.get("letter", "A"), "font": F(self.fs(190), True),
                      "bold": True, "color": C.GREEN, "gap": 0.05}]
            for line in s.get("sub", []):
                items.append({"text": line, "size": 40, "color": C.TEXT, "gap": 0.26})
            self.stack(items, self.H * 0.50)

        elif kind == "keyfind":
            self.kicker(s.get("kicker", "THE FINDING"))
            size = 92
            while True:
                font = F(self.fs(size), True)
                lines = self.wrap(s["body"], font, self.body_width())
                if len(lines) <= 3 or size <= 34:
                    break
                size -= 4
            asc, desc = font.getmetrics()
            lh = (asc + desc) * 1.24
            y = (self.H - lh * len(lines)) / 2 + self.fs(30)
            for line in lines:
                self.d.text((self.W / 2, y), line, font=font, fill=C.TEXT, anchor="ma")
                y += lh

        elif kind == "elim":
            right = s.get("verdict") == "right"
            tint = C.GREEN if right else C.RED
            self.kicker(s.get("kicker", ""), color=tint)

            y = self.H * 0.225
            if s.get("option"):
                letter, text = s["option"]
                card_h = self.fs(112)
                self.d.rounded_rectangle(
                    [self.margin, y, self.W - self.margin, y + card_h],
                    radius=self.fs(12), fill=(24, 28, 35), outline=tint, width=2)
                self.d.text((self.margin + self.fs(30), y + card_h / 2), letter,
                            font=F(self.fs(34), True), fill=tint, anchor="lm")
                tf = F(self.fs(29), False)
                tlines = self.wrap(text, tf, self.W - 2 * self.margin - self.fs(100))[:2]
                t_asc, t_desc = tf.getmetrics()
                t_lh = (t_asc + t_desc) * 1.18
                ty = y + card_h / 2 - (t_lh * len(tlines)) / 2
                for line in tlines:
                    self.d.text((self.margin + self.fs(96), ty), line, font=tf,
                                fill=C.TEXT, anchor="la")
                    ty += t_lh
                y += card_h + self.fs(44)

            avail_top = y
            avail = self.H - self.margin * 1.15 - avail_top
            size = 34
            while True:
                bf = F(self.fs(size), False)
                blines = self.wrap(s["body"], bf, self.body_width())
                b_asc, b_desc = bf.getmetrics()
                blh = (b_asc + b_desc) * 1.34
                if blh * len(blines) <= avail or size <= 18:
                    break
                size -= 2

            bait_lines: list[str] = []
            bf2 = F(self.fs(26), False)
            bait_h = 0.0
            if s.get("bait"):
                bait_lines = self.wrap(s["bait"], bf2, self.body_width())
                bait_h = self.fs(34) + self.fs(40) + self.fs(36) * len(bait_lines)

            body_h = blh * len(blines)
            y = avail_top + max(0.0, (avail - body_h - bait_h) * 0.42)

            for line in blines:
                self.d.text((self.W / 2, y), line, font=bf, fill=C.TEXT, anchor="ma")
                y += blh

            if bait_lines:
                y += self.fs(34)
                self.d.text((self.W / 2, y), "WHAT WOULD HAVE MADE IT RIGHT",
                            font=F(self.fs(22), True), fill=self.accent, anchor="ma")
                y += self.fs(40)
                for line in bait_lines:
                    self.d.text((self.W / 2, y), line, font=bf2, fill=C.MUTED, anchor="ma")
                    y += self.fs(36)

        elif kind == "pause":
            self.d.text((self.W / 2, self.H * 0.43), "PAUSE", font=F(self.fs(86), True),
                        fill=C.TEXT, anchor="mm")
            self.d.text((self.W / 2, self.H * 0.54), "Commit. Then keep watching.",
                        font=F(self.fs(32), False), fill=C.MUTED, anchor="mm")
            r = self.fs(9)
            for i in range(3):
                cx = self.W / 2 + (i - 1) * self.fs(44)
                self.d.ellipse([cx - r, self.H * 0.62 - r, cx + r, self.H * 0.62 + r],
                               fill=self.accent if i == 0 else (55, 62, 74))

        elif kind == "rule":
            rows = s["rows"]
            card_h = self.fs(140)
            gap = self.fs(24)
            block = len(rows) * card_h + (len(rows) - 1) * gap
            top = self.H * 0.53 - block / 2
            self.kicker(s.get("kicker", "THE RULE"))
            for i, (left, right, color) in enumerate(rows):
                y0 = top + i * (card_h + gap)
                self.d.rounded_rectangle([self.margin, y0, self.W - self.margin, y0 + card_h],
                                         radius=self.fs(14), fill=(21, 25, 32),
                                         outline=color, width=3)
                self.d.text((self.margin + self.fs(34), y0 + card_h / 2), left,
                            font=F(self.fs(36), True), fill=color, anchor="lm")
                self.d.text((self.W - self.margin - self.fs(34), y0 + card_h / 2), right,
                            font=F(self.fs(36), False), fill=C.TEXT, anchor="rm")

        elif kind == "outro":
            self.d.text((self.W / 2, self.H * 0.28), s.get("kicker", "NEXT"),
                        font=F(self.fs(24), True), fill=self.accent, anchor="ma")
            self.d.text((self.W / 2, self.H * 0.40), s.get("big", ""),
                        font=F(self.fs(88), True), fill=C.TEXT, anchor="ma")
            y = self.H * 0.54
            for line in s.get("sub", []):
                self.d.text((self.W / 2, y), line, font=F(self.fs(36), False),
                            fill=C.MUTED, anchor="ma")
                y += self.fs(58)

        self.wordmark(idx, total)
