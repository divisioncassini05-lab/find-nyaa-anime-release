---
name: find-nyaa-anime-release
description: Find and verify Nyaa anime releases, track with qBittorrent, and optionally sync watched episodes to Bangumi. Read personal Bangumi lists, ratings and comments for library questions or recommendations. Default minimums are 1 GiB per regular episode and 10 GiB per movie.
---

# Find Nyaa Anime Release

Run commands from this skill directory. Read the matching workflow and load its
supporting references only when needed.

| Request | Read next |
| --- | --- |
| First use, Bangumi list/progress, personal recommendations, or "I finished/watched" | [bangumi-sync.md](references/bangumi-sync.md) |
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

- On first use in each host, run `python scripts/watch.py bangumi status`. If not
  connected, show its official token setup link and ask the user to configure a
  local token file/environment variable, never to paste a token into chat. Do not
  claim cloud sync without authorization. Read bangumi-sync.md for setup and writes.
- Bangumi is an optional personal-library mirror, not a search/download authority.
  Never let its progress, collection status or availability override local targets,
  quality or delivery decisions. Accepted regular-episode delivery counts as watched;
  explicit watched/finished requests also write back. Link-only and failed adds do not.
  Read ratings/comments only for relevant personal-library questions or recommendations;
  use bounded queries, not a full-library dump on every search.
- The Agent establishes identity, episode numbering and selection from complete
  listings and details. Use [single-episode review](references/agent-review.md) or
  [season/movie review](references/package-review.md). Every add needs fresh
  validation and its matching process-local capability; raw magnets and serialized
  pass reports cannot authorize delivery.
- v3 is the local delivery ledger and Bangumi cache/outbox. Recover pending work by its original
  operation/hash before new retrieval. Only matching accepted receipts and committed
  progress count as delivery. Cloud writes retry independently of downloads.
  A scheduled run delivers at most one resource.
- Check-only/link-only/no-download skips submission and progress changes. A missing
  scheduled track is not recreated; completed tracks only finish scoped cleanup.
  Confirm completion independently of download progress or expected end dates.
- Keep evidence in the run directory returned by `watch.py workspace`. The retrieval
  workflow owns cleanup; retain inputs needed by unfinished operations.

For maintenance, use [architecture-v3.md](references/architecture-v3.md): isolated
copies, captured pages and fake clients, with deployment hash checks.
