"""VIGNETTE - faceless USMLE Step 1 question channel. Brand + render constants."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"

# ------------------------------------------------------------------ brand
BRAND = "QBANK"
HANDLE = "@qbank"
BRAND_SPOKEN = "Q bank"  # what the voice says, so TTS does not spell it out
TAGLINE = "Every wrong answer, explained."
DISCLAIMER = (
    "Educational content only. Not medical advice. "
    "Always follow your institution's protocols and current guidelines."
)

# ------------------------------------------------------------------ video
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
FPS = 30

VOICE = os.getenv("VOICE", "en-US-AndrewNeural")
RATE = os.getenv("RATE", "-5%")
TAIL_PAD = 0.35

# questions per long-form video
QUESTIONS_PER_VIDEO = int(os.getenv("QUESTIONS_PER_VIDEO", "2"))
MAX_SECONDS = 900  # hard ceiling, matches the Velocity workflow check

# ------------------------------------------------------------------ look
BG = (14, 17, 22)
TEXT = (240, 243, 247)
MUTED = (138, 148, 163)
FAINT = (60, 68, 80)
GREEN = (48, 164, 108)
RED = (229, 72, 77)
AMBER = (245, 165, 36)

SYSTEM_ACCENT = {
    "cardiology": (229, 72, 77),
    "renal": (62, 158, 255),
    "endocrine": (245, 165, 36),
    "id": (48, 164, 108),
    "heme": (168, 85, 247),
    "pharm": (236, 112, 99),
    "neuro": (233, 61, 130),
    "biostats": (148, 163, 184),
    "obgyn": (214, 93, 168),
    "peds": (86, 189, 199),
    "resp": (99, 179, 237),
    "gi": (196, 148, 90),
}

SYSTEM_LABEL = {
    "cardiology": "CARDIOLOGY",
    "renal": "NEPHROLOGY",
    "endocrine": "ENDOCRINE",
    "id": "INFECTIOUS DISEASE",
    "heme": "HEMATOLOGY",
    "pharm": "PHARMACOLOGY",
    "neuro": "NEUROLOGY",
    "biostats": "BIOSTATISTICS",
    "obgyn": "OB/GYN",
    "peds": "PEDIATRICS",
    "resp": "RESPIRATORY",
    "gi": "GASTROENTEROLOGY",
}

# ------------------------------------------------------------------ captions
CAP_MAX_WORDS = 11
CAP_MAX_CHARS = 78
CAP_LINE_CHARS = 40
CAP_ACCENT_ASS = "&H24A5F5&"  # ASS colours are BGR

# Only used when burn-in is enabled. False = plain white, one event per cue.
CAPTION_HIGHLIGHT = os.getenv("CAPTION_HIGHLIGHT", "0") == "1"

# Burned-in subtitles duplicate the slide text in this format, so they are off by
# default. The .srt sidecar still ships and drives YouTube's CC button.
# Override with BURN_CAPTIONS=1 or `build.py --burn-captions`.
BURN_CAPTIONS = os.getenv("BURN_CAPTIONS", "0") == "1"

# ------------------------------------------------------------------ tools
def _first_existing(*paths: str | Path) -> Path:
    for p in paths:
        if Path(p).exists():
            return Path(p)
    return Path(paths[-1])


_win_ffmpeg = Path(r"C:\ffmpeg\bin\ffmpeg.exe")
_win_ffprobe = Path(r"C:\ffmpeg\bin\ffprobe.exe")

FFMPEG = os.getenv("FFMPEG") or (str(_win_ffmpeg) if _win_ffmpeg.exists() else "ffmpeg")
FFPROBE = os.getenv("FFPROBE") or (str(_win_ffprobe) if _win_ffprobe.exists() else "ffprobe")

FONT_DIR = Path(os.getenv("FONT_DIR", r"C:\Windows\Fonts" if Path(r"C:\Windows\Fonts").exists()
                          else "/usr/share/fonts/truetype"))

FONT_REGULAR = _first_existing(
    FONT_DIR / "segoeui.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    FONT_DIR / "DejaVuSans.ttf",
)
FONT_BOLD = _first_existing(
    FONT_DIR / "segoeuib.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    FONT_DIR / "DejaVuSans-Bold.ttf",
)
