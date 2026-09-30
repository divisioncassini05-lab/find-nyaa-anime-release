# v3 failure recovery

Preserve the originating work/season/part, episode intent, quality limits, subtitle
policy and download mode. A retry reason or Chinese display title never adds hard
Chinese. Scheduled defaults and memory/rrule recovery are defined once in
[scheduled-new-anime.md](scheduled-new-anime.md); do not create retry child tasks for
that template. Existing tasks retain their explicit rules unless the user changes them.

## Identify the failed stage

| Evidence | Required action |
| --- | --- |
| Identity/numbering/provider conflict | Preserve the bound identity. Inspect independent official evidence, resolve a real choice with the user if necessary. No download or timed retry. Repairs use the v3 domain command with reviewed evidence, never direct JSON merge. |
| Official future premiere, hiatus or split-cour gap | Record/report verified timing. Do not infer actual release or completion; no four-hour resource retry during known non-airing periods. |
| Query failure/incomplete listing | Coverage is incomplete, not an empty release result. Retain classified diagnostics and inspect the actual coverage gap. |
| Complete search with no new target | Report scoped absence; in the new scheduled template this can trigger bounded same-task supplementation. Last week's handled episode does not complete this week's window. |
| Candidates fail quality/size/hard subtitles | Retain the target, minimum and explicit maximum. Only explicit upward compatibility allows exceeding a named tier's preferred ceiling; never return an older episode. |
| Detail/review evidence incomplete | Complete the raw evidence. Candidate changes before an operation exists require a new Agent review; do not silently substitute. |
| discovery_changed / candidate_details_changed | Read the refreshed scope/details and redo review. Never narrow the query to make changed rows disappear. |
| coverage_review_required / latest_unresolved | Complete semantic review of full evidence, not a parser shortlist. |
| available_enqueue_failed / recovery_failed | Preserve the operation and exact hash. Recover it; do not restart title search. |
| accepted_receipt_commit_failed | Client accepted but v3 commit failed. Retain ledger/evidence and use recover for the same operation. Never manually advance progress. |
| Permission or automatic approval rejection | Report the exact action/reason. No scheduler/config/shell workaround or ordinary network retry. |
| completed / cleanup_pending | Follow completion.md; only outbox cleanup remains. No new discovery or torrent submission. |

## Discover and review using current v3 commands

```powershell
python scripts/watch.py discover "VERIFIED SEARCH TITLE" --latest --output "RUN_DIR/LISTING.json"
python scripts/watch.py detail CANDIDATE_ID --output "RUN_DIR/DETAIL.json"
python scripts/watch.py review --manifest "RUN_DIR/REVIEW.json" --tier browse --want-zh --allow-upward-compatibility
```

Carry actual user overrides in both review and deliver. Read all rows in the native
chronological listing; additional pages/verified aliases must address a real coverage
gap. A Chinese-only query, newest upload, or a planned air date cannot establish latest.
Use fresh evidence for a later scheduled retry; do not reuse an old negative as a new
search. Do not import legacy fixed-shortlist, keyword rewriting, seven-day rescue or
candidate-id finalization instructions into the reviewed v3 path. Independent search
results do not advance tracking; no direct legacy writer is permitted.

Before preparing an operation, qualified alternatives can be compared and reviewed.
After preparing one, recovery remains bound to its operation_id and info_hash.
Stop when coverage is sufficient or a real stage remains blocked; report the checked
scope and actual rejection. Do not claim universal absence.

## Transport recovery boundaries

The shared http_transport recovers eligible GETs only, never torrent submissions.
Timeout/EOF/reset/DNS/incomplete-read/502/503/504 recovery is bounded by its request
budget. Keep returned orchestration/session IDs and await the existing command;
empty output does not mean exit. Do not stack another identical command on top.

Certificate failures are not transient release absence. Keep hostname and certificate
verification enabled. The Windows native curl fallback, when eligible, preserves
proxy/trust constraints; do not add --insecure, switch routes, modify proxy settings
or install a fetched CA. HTTP permission failures are not rerouted. Classify
`tls_certificate_verify_failed`, `tls_user_context_unavailable`, exhausted transport,
and ordinary transient network failures separately.

For an execution-context failure use the execution tool's permitted approval route
for the same read-only diagnostic or original-operation recovery. Never repeatedly
retry an unchanged restricted context. Report trust/context failures without scheduling
resource retries. Preserve diagnostics without credentials in the run memory.

## Recover the exact delivery operation

```powershell
python scripts/watch.py recover --operation OPERATION_ID
```

Use the original client adapter and explicit profile/save-path configuration when
non-default. The v3 ledger retains the operation before preflight; do not follow old
instructions saying no journal/operation exists until the desktop is launched.
Recover accepted entries by committing their receipt; if no accepted receipt was
persisted, inspect that same hash before any send. A committed operation never submits
again. Only already_present/submitted/submitted_verified with matching acceptance
can advance progress; downloading to completion is unnecessary.

- `client_context_required`, `startup_unverified`, `startup_exited_without_client`,
  `handoff_unverified`: follow the returned RecoveryAction. Where indicated, request
  execution-tool approval for the complete `watch recover` in the normal Windows user
  context after the original process finishes. Starting only the GUI is insufficient.
  Existing download intent does not override tool permissions. One approved-context
  recovery is enough to establish whether it works; stop and retain diagnostics if it
  fails. A zero exit code or running process is not receipt evidence.
- `client_busy`: await/inspect the existing command or client lock; no parallel enqueue.
- `permission_denied`, authentication failure, missing executable, unknown/permanent
  errors: diagnose/report, never relabel as temporary resource/network absence.
- Inspect exact matching metadata/fastresume or authenticated API evidence. Do not
  automatically enable Web UI or change credentials as a workaround.
- RecoveryAction.retryable does not authorize scheduled retry. Current client recovery
  has scheduled_retry_allowed=false; resource/network retry permission does not cover
  client startup failures. The standard template restores the regular schedule and
  reports a client recovery need instead of a blind four-hour client retry.

If recovery commits a delivery this run, do not immediately submit a second episode.
Then reconcile completion and drain outbox as applicable. Artifact cleanup is allowed
only after durable commit or with pending-operation references preserved.

## Scheduled failure handling

Use the fixed template's read-only planner to decide finite resource retries. It
computes at most three checks four hours apart on the original task and restores the
base schedule on success, exhaustion or a nonretryable result. Read back before claiming
that a schedule changed. Do not carry last week's success into the next window.

The automation memory records scheduling intent/count/window, not authoritative
progress. Save intent before changing the app schedule. An uncertain update is resolved
by reading the exact task, not by creating another. Failure to save intent prevents a
new temporary schedule; if a prior temporary schedule exists, restore the base through
the app tool and report that outcome independently. An unapplied or uncertain plan must
never be reported as scheduled. Follow completion cleanup before ordinary retry handling.
