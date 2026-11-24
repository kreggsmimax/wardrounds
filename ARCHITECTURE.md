# Velocity Medical — architecture

The Velocity bots are a content factory: AI writes, TTS speaks, Playwright renders, the
uploader posts, cron repeats. That works because a bad Spanish phrase is cosmetic.

Medicine is different. The error *is* the product, and YouTube treats health content as a
heightened-enforcement category. So this pipeline keeps the factory and adds one thing
Velocity doesn't have: **a gate between generation and publication.**

## The one structural change

```
VELOCITY                          VELOCITY MEDICAL
────────                          ────────────────
AI authors facts + prose    →     ledger holds facts
                                  AI authors prose around fixed slots
                                  verifier checks slot fidelity + claims
                                  → new: human approval queue
                                  render
                                  upload
```

The model is never asked for a potassium value. It is handed
`{"K": 3.1, "HCO3": 31, "renin": "suppressed"}` and writes sentences with those pinned.
A validator confirms every pinned value survived into the narration. If one goes missing,
the build fails instead of publishing.

## Data flow

```
data/questions.json            reviewed questions, versioned in git
        │
        ├─ engine/facts.py      validate → pick (system spread, no repeats)
        │
        ├─ engine/script.py     ledger entry → scene list (renderer spec)
        │         │
        │         └─ AI writes ONLY the connective narration
        │            around fixed slots, one call per beat
        │
        ├─ engine/verify.py     second model, fixed checklist, must quote source
        │         │
        │         └─ fail → regenerate (max 3) → escalate to pending
        │
        ├─ engine/tts.py        Edge TTS + WordBoundary word clocks
        ├─ engine/frames.py     Pillow scene renderer  ← already working
        ├─ engine/captions.py   .srt + burned .ass      ← already working
        ├─ engine/render.py     ffmpeg assembly
        ├─ engine/seo.py        title / description / tags
        ├─ engine/thumbnails.py HTML → PNG
        │
        └─ build.py             orchestration → output/latest_video.json
                 │
                 └─ .github/workflows/daily.yml  →  cron → YouTube
```

## Module map against Velocity

| Velocity file | Medical equivalent | Effort |
|---|---|---|
| `config.py` | `config.py` — brand, system palette, target length | port |
| `engine/content.py` | `engine/script.py` — slot-filling, not fact generation | **rewrite** |
| — | `engine/facts.py` — ledger + validator | **done** |
| — | `engine/verify.py` — second-model gate | new |
| `engine/tts.py` | `engine/tts.py` — plus `boundary="WordBoundary"` | port |
| `engine/timeline.py` | `engine/timeline.py` — same idea, fewer beat types | port |
| `engine/renderer.py` | `engine/frames.py` + `render.py` | **done** (see `../video/`) |
| `engine/audio.py` | drop — no music under medical narration | drop |
| `engine/thumbnails.py` | same | port |
| `engine/seo.py` | same, new title formula | port |
| `build.py` | same | port |
| `upload_to_youtube.py` | same | port |
| `upload_to_facebook.py` | same, optional | port |

Three genuinely new files. Everything else is a rename with different constants.

## The approval gate

This is the part that makes daily cadence safe.

```
Week 1, Sunday, 20 minutes:
  open output/review/queue.md
  → 30 drafted questions, each with: vignette, answer, sources, verifier verdict
  → mark approved / rejected / needs-work
  → git commit

Mon–Sat:
  cron picks approved entries, renders, uploads. No human.
```

Batch review, not daily production. 20 minutes buys you a week of daily uploads.

The queue is a git-tracked file, so every published claim has a date and a reviewer.

## Cadence math

| | Value |
|---|---|
| Render time, 10-min video | ~45–60 min on a 2-core runner |
| Minutes per day | ~55 |
| Minutes per month | ~1,650 |
| GitHub free tier (private repo) | 2,000 min/month |
| GitHub free tier (public repo) | unlimited |

**Run public.** At daily cadence a private repo sits at 82% of the free quota with
nothing left for retries. Your 34 language bots must already be public for the same
reason.

YouTube limits: roughly 15 uploads/day for a new unverified channel, rising with account
standing. One long-form + one Short per day is well inside that.

## Recommended ramp

| Phase | Long-form | Shorts | Why |
|---|---|---|---|
| Weeks 1–8 | 3/week | 1/day | Watch retention before scaling the format |
| Weeks 9–16 | 5/week | 1/day | Format proven, add volume |
| Week 17+ | 1/day | 1/day | Factory at full rate |

Daily from day one is technically possible. It is a bad idea for exactly one reason:
you would be scaling a format whose hooks you have never seen data on.

## Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Wrong clinical fact published | Fatal to the channel | Fact ledger + verifier + human approval queue |
| YouTube health-content enforcement | High | Disclaimer every video, no dosing or treatment directives, cite sources in description |
| Copyright (UWorld/Amboss/NBME recall) | High | Ledger entries must be original; no "recall" submissions accepted |
| Image licensing | Medium | Only public-domain or licensed sources; log per video |
| AI content flagged as low-effort | Medium | Original visuals, original questions, real reasoning — not stock footage |
| Impersonating a physician | High | No "Dr"/"MD" in brand; state in About that content is educational |

## Build order

| # | Piece | Status |
|---|---|---|
| 1 | `engine/facts.py` + `data/questions.json` | **done**, validator self-tested |
| 2 | `engine/script.py` — ledger → scene list | **done**, deterministic (no model call) |
| 3 | `engine/verify.py` — the gate | **done**, blocks pending + dropped numbers |
| 4 | `engine/frames.py` + `engine/render.py` | **done**, 6 min video in ~3 min |
| 5 | `engine/seo.py`, thumbnail, `upload_to_youtube.py` | **done**, upload needs OAuth |
| 6 | `.github/workflows/daily.yml` | written, not yet run |
| 7 | 9:16 Shorts scene list | not built |

## What the gate caught on the first run

`verify.py` refused to render the biostatistics question because its stem did not match
the USMLE question form and its vignette was under the word floor. The fix was to relax
the *rule*, not the question — biostat stems legitimately read "what is the probability".
That is the correct failure mode: the gate argues with you, and you decide.

## Still open

- **Slot fidelity for AI prose.** Right now `script.py` is fully deterministic and needs
  no model. If an AI layer is added later to vary phrasing, it must be constrained to
  rewrite only the connective sentences, with `verify.py` diffing numbers before and
  after. Do not let it touch a claim.
- **Short-form.** The renderer already handles 1080×1920 and `write_ass` adjusts margins
  for the Shorts UI. It needs a scene list that cuts at the pause card.
