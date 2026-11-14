---
name: find-nyaa-anime-release
description: Find and verify Nyaa anime releases, track with qBittorrent, and optionally sync watched episodes to Bangumi. Read personal Bangumi lists, ratings and comments for library questions or recommendations. Default minimums are 1 GiB per regular episode and 10 GiB per movie.
---

# Find Nyaa Anime Release

Run commands from the absolute resource directory supplied by DSH, not the chat workspace.
Use DSH file/terminal tools and an installed Python 3.11+ (python, python3, or py -3).
Default to a DSH full-access session for this skill. When already full access, omit
`sandbox_permissions` (an escalation request, not a session-mode setting). Follow the live
terminal schema, including required justification for any permitted escalation.
Reuse session authorization; do not ask separately for every directory.
If the session is restricted, ask once to switch to full access; the skill cannot grant host permissions.
Only for an actual environment failure, use `python scripts/dsh_doctor.py` (read-only). No install-time commands run.
Never use Codex tools, local Codex records or an assumed model/browser API. For creating
or changing schedules and cleanup, read [DSH host integration](references/dsh-host-runtime.md).
Read the matching workflow and load supporting references only when needed.

Use compact evidence output as described in the retrieval workflow. Reuse complete
reports already read; do not dump the entire library, source code or all references
for routine searches. Delivery performs its own fresh audit. Optional integration
failure must not trigger a repeated search, weaker constraints or a retry loop.
Efficiency must not reduce search coverage or evidence quality: retain every
candidate, resolve uncertain names/formats, and use necessary web fallback.
Never skip identity, episode, size or required-subtitle checks to save tokens.

In DSH, use the native Anime tracking panel for plans and Bangumi/qBittorrent
configuration. Provide usage guidance only on request; do not open Python
setup windows automatically. Optional setup
never blocks link-only searches. Headless users may use private file/env setup.
For every `[anime-plan:ID]` search, manual or scheduled, start with
[panel-search.md](references/panel-search.md), not the generic scheduled-run route below.
Read [panel-management.md](references/panel-management.md) for UI/plan management.
Panel task execution marks non-watched works as watching; progress and completion
writes require a user button click. Keep completed download history locally;
this overrides the chat delivery-mirroring and cleanup defaults below.
Never request credentials in chat. Background runs do not show onboarding.

| Request | Read next |
| --- | --- |
| Introduction, usage tutorial, examples, or "how do I use this?" | [getting-started.md](references/getting-started.md) |
| Bangumi list/progress, personal recommendations, or "I finished/watched" | [bangumi-sync.md](references/bangumi-sync.md) |
| Interactive search/download, next/latest/exact release, season/movie | [search-flow.md](references/search-flow.md) |
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

- Bangumi authorization is entered only in the local setup window (manual file/env
  configuration remains supported). Never ask for tokens in chat or claim cloud
  sync without authorization. Read bangumi-sync.md for setup and writes.
- Bangumi is an optional personal-library mirror, not a search/download authority.
  The host-local record remains authoritative for the active `watching` list, next
  episode and schedule. Bangumi may be read for the user's recorded library,
  ratings, comments and recommendations without changing local tracking. Never let
  its progress, collection status or availability override local targets, quality
  or delivery decisions.
- Bangumi writes are different: accepted regular-episode delivery counts as watched,
  and explicit watched/finished or explicit collection-status instructions may write
  back. Link-only and failed adds do not. Do not infer a sync request from a casual
  mention or complaint; “put it on hold” and “drop it” are explicit, while “I do not
  feel like watching it” is not.
- Read-only Bangumi access may be used for a relevant list, history or recommendation
  question. It must not be used merely because an unrelated title happened to appear
  in ordinary conversation. Use bounded queries, not a full-library dump on every
  resource search.
- Keep found, accepted by the download client, downloaded and watched distinct.
  Before a Bangumi write, confirm the account, exact work/season and requested
  episode scope; never overwrite ratings/comments/tags. Report pending or partial
  writes honestly and verify by readback. See bangumi-sync.md for host boundaries.
- The Agent establishes identity, episode numbering and selection from complete
  listings and details. Use [scripted search](references/search-flow.md); scripts
  assemble reviews from semantic decisions. Every add needs fresh
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
