# Going live

Four blockers stand between the current repo and a channel that publishes every day
without you. `python preflight.py` reports all four with live status.

## 1. Push to a public GitHub repo

```powershell
cd "D:\E agy cli\E youtube bots\USMLE-channel\bot"
git remote add origin https://github.com/<you>/vignette.git
git branch -M main
git push -u origin main
```

**Public, not private.** A daily run is ~55 CI minutes. That is ~1,650 min/month against
GitHub's 2,000 free quota on private repos — no headroom for retries.

## 2. Add the three YouTube secrets

Settings → Secrets and variables → Actions → New repository secret:

| Name | Where it comes from |
|---|---|
| `YT_CLIENT_ID` | Google Cloud OAuth client (Desktop) |
| `YT_CLIENT_SECRET` | same client |
| `YT_REFRESH_TOKEN` | one-time OAuth consent flow |

If your other bots already publish, reuse their values — the uploader is the same shape.

## 3. Fill the ledger

This is the only real work left, and it is arithmetic:

| Video length | Questions/day | Cooldown | **Minimum approved** |
|---|---|---|---|
| 1 question | 1 | 21 days | **21** |
| 2 questions | 1 | 21 days | **42** |
| 2 questions + Short | 1 | 21 days | **42** |
| 2 questions | 2 | 21 days | **84** |

At 42, the ledger recycles every three weeks and the channel never stops. Below that,
`build.py` refuses to publish rather than repeat yesterday's question — which is the
correct failure.

To add one, append to `data/questions.json`:

```json
{
  "id": "system-topic-001",
  "system": "cardiology",
  "topic": "Aortic stenosis",
  "difficulty": 2,
  "hook": "One sentence that names the trap.",
  "vignette": "Full long-form stem, 40-190 words.",
  "short_vignette": "Two sentences for the vertical cut. Optional.",
  "stem": "Which of the following ...?",
  "options": [
    {"letter": "A", "text": "...", "correct": true,
     "why": "Why this is right.",
     "would_make_right": "Nothing - this is the answer."},
    {"letter": "B", "text": "...", "correct": false,
     "why": "Why this is the trap.",
     "would_make_right": "The vignette detail that would have made B correct."}
  ],
  "rule": "The transferable one-liner.",
  "sources": ["First Aid ...", "Guideline ..."],
  "review": {"status": "pending", "by": "", "date": "", "note": ""}
}
```

Then validate:

```powershell
python build.py --list
```

It fails loudly on a structural problem before anything renders. Flip `status` to
`approved` and put your name in `by` only after you have checked every value.

## 4. Test the first run manually

```powershell
python preflight.py          # should say READY TO PUBLISH
python build.py --shorts     # local build, no upload
```

Then in GitHub: Actions → *Vignette - Daily Question Set* → **Run workflow**, with
`skip_upload` ticked the first time. Watch the run. When it is green, run it again with
upload enabled and confirm the video appears as `private`. Then flip `privacy` to
`public` in `build.py`.

## Steady state

```
Sunday, 20 min:  review pending entries → set status "approved" → git push
Mon-Sat:         cron 40 15 * * * → build → verify → upload. Nobody involved.
```

The cron is UTC. `40 15 * * *` is 21:10 IST, 15:40 UTC.

## If a run fails

| Symptom | Cause | Fix |
|---|---|---|
| `VERIFICATION FAILED - refusing to render` | a number was dropped or an entry is unapproved | read the message, fix the entry. Do not bypass. |
| `Not enough fresh questions` | ledger exhausted inside the cooldown | add approved entries, or lower `QUESTIONS_PER_VIDEO` |
| `TTS failed after 6 attempts` | Edge endpoint throttling | re-run; audio cache means finished lines are not re-paid |
| `quotaExceeded` on upload | YouTube daily upload cap | expected above ~10/day on a new channel |
| `invalid_grant` | refresh token revoked | redo OAuth, replace the secret |
