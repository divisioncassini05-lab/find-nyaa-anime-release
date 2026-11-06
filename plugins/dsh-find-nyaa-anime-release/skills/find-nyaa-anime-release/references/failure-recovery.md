# v3 failure recovery

Preserve the originating work/season/part, episode intent, quality limits, subtitle
policy and download mode. A retry reason or Chinese display title never adds hard
Chinese. Scheduled execution follows [scheduled-run.md](scheduled-run.md); load
[scheduled-retry.md](scheduled-retry.md) only for retry or schedule reconciliation.
The creation template is not needed during recovery. Do not create retry child
tasks. Existing tasks retain their explicit rules unless the user changes them.

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
| Windows firewall or first-run confirmation prompt | Follow [client-readiness.md](client-readiness.md). Inspect the actual executable and network profile; this is environment setup, not release absence. Preserve any original operation/hash and accepted receipt. Do not repeatedly launch, re-enqueue or schedule a resource retry to dismiss the prompt. |
| completed / cleanup_pending | Follow completion.md; only outbox cleanup remains. No new discovery or torrent submission. |

## Resume the appropriate stage

Use [retrieval-workflow.md](retrieval-workflow.md) to repair incomplete evidence
before an operation exists. Later retries need fresh evidence rather than an old
negative result. Once prepared, recovery stays bound to operation_id and info_hash.

## Transport recovery boundaries

After an exhausted request, use `python scripts/network_doctor.py` once when a
diagnosis is needed. It checks the effective proxy TCP endpoint and a real Nyaa
listing without changing settings or touching delivery/progress. An open local
proxy port does not establish Nyaa reachability. A native curl fallback shares the
same route; changing HTTP clients does not prove an independent network path.

Use `transport.scheduled_outcome` and the complete attempt chain:

| Result | Handling |
| --- | --- |
| `network_transient`, including exhausted EOF/handshake/reset/timeout and eligible 502/503/504 | Preserve incomplete coverage; scheduled runs use the existing bounded retry planner. |
| `tls_certificate_verify_failed`, `tls_user_context_unavailable`, permission/authentication failure | Diagnose the specific trust/context/permission issue; no ordinary resource retry. A specific failure takes precedence over a later generic handshake error. |
| Inspected HTTP challenge/403 | Report the actual response; a TLS EOF alone is not Cloudflare evidence. |
| Unknown error | Diagnose before assigning a retry class. |

`http_transport` already bounds eligible GET retries. Keep certificate/hostname
verification enabled. For execution-context failures use the tool's permitted
approval route for the same diagnostic or original-operation recovery. Await a
still-running command by its returned session ID instead of stacking probes.
Record sanitized diagnostics in the existing run memory. Diagnostics never submit
torrents or advance progress.

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
- `client_installation_conflict`, `process_probe_failed`,
  `executable_version_unverified`,
  `client_independent_launch_failed`, `client_runtime_unverified`: follow
  client-readiness.md. Verify the installation/current-user runtime and preserve the
  same operation/hash. A lost broker response may still have created the client;
  re-inspect before recovery. No direct-child launch fallback or resource retry.
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

Finish failed scheduled runs through [scheduled-run.md](scheduled-run.md) and
[scheduled-retry.md](scheduled-retry.md). The planner handles bounded same-task
supplementation and restoration of the regular schedule. Persist intent before
an app update, then read back its result; an unapplied plan is not a scheduled
retry. Completion cleanup takes precedence. Automation memory is not progress.
