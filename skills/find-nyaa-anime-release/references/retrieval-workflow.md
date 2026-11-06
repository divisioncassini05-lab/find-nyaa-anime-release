# Retrieval and delivery

## Resolve the request

```powershell
python scripts/watch.py inspect "TITLE"
```

Explicit scope takes precedence over a unique tracked match. Verify work, year,
season/part, aliases and source numbering; a fuzzy provider match cannot bind them.
Preserve track IDs/provider bindings. Unknown season stays unknown. For new tracks
or legacy migration, read [airing-watch-state.md](airing-watch-state.md).
`--state PATH` goes before the watch subcommand.

- Interactive bare tracked title means next episode; scheduled bare title or
  explicit latest means the latest released regular episode.
- Apply SKILL.md's old/new interaction policy. For old-work choices, report
  coverage, size eligibility, subtitle evidence, decisive quality differences and
  current swarm counts. Each offered choice needs complete Nyaa details and an
  exact info hash from which a valid BTIH magnet can be derived; this is evidence
  of a usable submission identifier, not guaranteed transfer speed.
- Pending operations recover before new discovery. `completed` routes to
  [completion.md](completion.md). `finale_pending_evidence` without a target means
  waiting for completion evidence, not an invented next episode. Resolve `blocked`
  identity/evidence conflicts first. Missing scheduled tracks stay missing.
- Creating a schedule uses [scheduled-new-anime.md](scheduled-new-anime.md).
  Scheduled execution uses [scheduled-run.md](scheduled-run.md), including its
  ownership and retry handling. It uses the saved scope without opening a browser.

## Collect complete evidence

```powershell
python scripts/watch.py workspace
python scripts/watch.py discover "VERIFIED SEARCH TITLE" --latest --output "RUN_DIR/LISTING.json"
python scripts/watch.py detail CANDIDATE_ID --output "RUN_DIR/DETAIL.json"
```

Use the workspace's absolute `run_dir` for listings, details, reviews and temporary
inputs. If the CLI redirects an output, read its returned `output_path`.

Use a verified distinctive title, without invented episode/season suffixes. Read
all first-page titles, IDs, sizes, publication times and swarm counts in native
newest-publication order. Add `--page 2` or a verified alias when needed to resolve
a coverage gap. Newest upload, Chinese-only search and planned airing time cannot
alone establish the latest episode.

Read full descriptions and file lists of plausible candidates. Raw reports retain
all rows; read in chunks when truncated and reuse sufficient evidence. Resolve
selection-changing ambiguity before declaring scoped absence. Complete seasons
require joint interpretation of all filenames and parent directories; see
[package-review.md](package-review.md).

Apply the Nyaa source scope from SKILL.md. Search engines, if needed, target
`site:nyaa.si`; candidate evidence must come from the actual Nyaa detail. The normal
delivery path derives a magnet from its verified hash, without fetching a separate
magnet page or `.torrent` URL. `source_url` records provenance.

For request failures use [failure-recovery.md](failure-recovery.md). Preserve the
actual host/error and incomplete coverage; do not diagnose Cloudflare from a generic
TLS failure. Report an inaccessible candidate as unresolved, not as an available
choice or proof that no release exists.

## Review, validate and deliver

Apply [quality-ranking.md](quality-ranking.md) before selection. Preserve the
requested tier, bounds and subtitle/audio requirements in `quality_policy`, and
record the decisive comparison and uncertainty in `quality_comparison`.

For a single regular episode, follow [agent-review.md](agent-review.md):

```powershell
python scripts/watch.py review --track-id TRACK_ID --listing "RUN_DIR/LISTING.json" --detail "RUN_DIR/DETAIL.json" --intent latest_regular --episode N --tier browse --want-zh --output "RUN_DIR/REVIEW.json"
python scripts/watch.py review --manifest "RUN_DIR/REVIEW.json" --tier browse --want-zh
python scripts/watch.py deliver "TITLE" --review "RUN_DIR/REVIEW.json" --latest --tier browse --want-zh --include-magnet --legal-ok --enqueue-qbittorrent
```

The first command creates an **unreviewed** draft; fill it before audit/delivery.
Use the actual policy flags in all three commands. Repeat `--listing` for additional
evidence; use `specific_episode` or `next_tracked` for other intents as documented
in agent-review.md. Link-only requests return the audit's verified magnet without
delivery or progress updates.

Movies and complete seasons use [package-review.md](package-review.md), not the
single-video entrypoint, and do not create synthetic regular-series progress.
Delivery refetches details and reviewed latest-listing scope. Changed evidence
returns for review; it does not select a replacement or loosen conditions.

The normal client path verifies user context, independent launch and exact-hash
acceptance. For first setup, Windows prompts or client problems, use
[client-readiness.md](client-readiness.md). `--client webapi --qb-url URL` selects
an already configured Web API; credentials come from `QBITTORRENT_USERNAME` and
`QBITTORRENT_PASSWORD`, not reports. Launcher exit or HTTP success alone is not
receipt evidence.

## Recover and finish

```powershell
python scripts/watch.py recover --operation OPERATION_ID
```

Only `already_present`, `submitted` or `submitted_verified` with matching acceptance
can advance progress. A failed/ambiguous submission or receipt-commit failure
recovers its original operation/hash under the original policy. For package
recovery use its journal command in package-review.md. Client acceptance is distinct
from completed downloading. Recovery details are in failure-recovery.md.

When finale evidence or cleanup is relevant, use [completion.md](completion.md).
It covers reconcile, exact-owner outbox actions and full local-record deletion after
accepted finale delivery and official whole-scope completion. `cleanup_pending`
does not mean deletion succeeded. Downloaded media and client tasks are unaffected.

Committed delivery/recovery cleans its owned evidence automatically. End other
runs with `python scripts/watch.py cleanup --run RUN_DIR` after consuming the report;
pending-operation references protect recovery inputs. Preserve unpersisted receipts.
The collector's indexing and 48-hour sweep are documented in architecture-v3.md.

Report the work/episode, decisive selection evidence and actual acceptance or
unresolved stage briefly. Distinguish `local_record_deleted`, `cleanup_pending` and
`track_absent`; do not claim a future retry unless it was actually scheduled.
