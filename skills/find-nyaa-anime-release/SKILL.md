---
name: find-nyaa-anime-release
description: Find and verify Nyaa anime releases using full page evidence, and create or run scheduled anime tracking with qBittorrent. Supports latest/next/exact episodes, movies, seasons, subtitles and magnets. Default minimums are 1 GiB per regular episode and 10 GiB per movie.
---

# Find Nyaa Anime Release

Run commands from this skill directory. Read the matching workflow and load its
supporting references only when needed.

| Request | Read next |
| --- | --- |
| Interactive search/download, next/latest/exact release | [retrieval-workflow.md](references/retrieval-workflow.md) |
| Create/change an anime schedule | [scheduled-new-anime.md](references/scheduled-new-anime.md) |
| A scheduled run or retry | [scheduled-run.md](references/scheduled-run.md) |
| Recover an interrupted delivery | [failure-recovery.md](references/failure-recovery.md) |
| Completion or scoped cleanup | [completion.md](references/completion.md) |
| Client setup, Windows prompts, slow downloads or client exits | [client-readiness.md](references/client-readiness.md) |
| Nyaa connection/TLS failures | [failure-recovery.md](references/failure-recovery.md#transport-recovery-boundaries) |

## Source and selection

- Anime series, complete seasons and anime movies use `https://nyaa.si` by
  default. Other release sites require an explicit user request. Search engines
  may locate Nyaa pages; official sites supply identity/airing evidence.
- For interactive searches of airing/upcoming anime, use the saved defaults and
  proceed through review and delivery. Default: `browse` (1–2 GiB per regular
  episode), upward compatibility, Chinese subtitles as a soft preference.
- For old/completed catalogue anime, review the candidates and offer 2–4 eligible
  choices (fewer if fewer qualify), then deliver the user's choice. Explicit
  authorization to use the default or a named candidate skips this choice step.
  Scheduled runs use their saved policy; an old-work run without a saved selection
  or default-selection authorization reports choices and stops before delivery.
- Size is an eligibility constraint, not a quality score. Movies default to a
  10 GiB minimum. Preserve explicit limits and required subtitles/audio. See
  [quality-ranking.md](references/quality-ranking.md) for all tiers and comparison.

## Delivery and state

- The Agent establishes identity, episode numbering and selection from complete
  listings and details. Use [single-episode review](references/agent-review.md) or
  [season/movie review](references/package-review.md). Every add needs fresh
  validation and its matching process-local capability; raw magnets and serialized
  pass reports cannot authorize delivery.
- v3 is the sole progress authority. Recover pending work by its original
  operation/hash before new retrieval. Only matching accepted receipts and committed
  progress count as delivery. A scheduled run delivers at most one resource.
- Check-only/link-only/no-download skips submission and progress changes. A missing
  scheduled track is not recreated; completed tracks only finish scoped cleanup.
  Confirm completion independently of download progress or expected end dates.
- Keep evidence in the run directory returned by `watch.py workspace`. The retrieval
  workflow owns cleanup; retain inputs needed by unfinished operations.

For maintenance, use [architecture-v3.md](references/architecture-v3.md): isolated
copies, captured pages and fake clients, with deployment hash checks.
