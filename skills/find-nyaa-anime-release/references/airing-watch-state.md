# v3 tracking identity, state and migration

Read before establishing a scheduled target or interpreting a latest/next boundary.
The tracking repository is the sole progress authority. runtime_paths.py chooses the
existing Windows tracking file or the user's Downloads directory; ANIME_TRACKING_STATE
and the global `watch --state PATH` override it. Tests must always use a temporary path.

## Establish identity before delivery

Explicit work/season/part wins, followed by a unique current local match and verified
external evidence. Registered aliases select that installment, not the first fuzzy
provider result. Multiple current matches need resolution. A different season gets a
separate identity, never inherited progress. Keep provider season coverage, split-cour
part and release numbering distinct; preserve unknown values as unknown.

Each record has track_id, revision and identity_revision. Preserve track IDs and
provider bindings through migration and normal retrieval. Shared aliases/IDs do not
authorize merging or deletion. Resolve a binding conflict with reviewed independent
identity evidence through the repository's repair_identity command; never adjust a
record merely to fit a selected candidate. Pending operations lock identity revision.

Inspect before creating:

```powershell
python scripts/watch.py inspect "TITLE"
python scripts/watch.py create --track-id TRACK_ID --identity "RUN_DIR/IDENTITY.json"
```

IDENTITY.json is a create_track command payload with `identity` and optional
`broadcast`, not a flat legacy row. Use verified title/aliases/season/part/provider
bindings and known episode total. A scheduled future premiere can be bound before
airing; initial progress stays zero and the date does not prove a release. Ambiguity
must be resolved before create. For all temporary inputs use an owned workspace and
register externally written JSON with evidence_artifacts.register.

## One state model and transaction boundary

- identity and broadcast store scope, binding and completion evidence.
- progress.handled_episode is the highest accepted regular-episode delivery.
- progress.latest_release_episode is the latest episode confirmed by evidence.
- progress.target_episode is nullable; next_episode is a report projection only.
- lifecycle.phase is airing, finale_pending_evidence, completed or blocked.
- deliveries, operations and outbox preserve receipts, recoverable work and actions.

Only StateRepository/domain commands write this state under locks and revision checks.
No flat projection, alternate writer, manual JSON progress edit or old record-found
command is allowed. A link-only magnet does not advance handled progress. Neither do
movies, batches, specials, discovery results, review approval or failed client handoff.

## Delivery and recovery

Use watch deliver after full review. The operation is persisted before preflight and
client submission. Only matching accepted receipts with already_present, submitted or
submitted_verified advance progress. Video download completion is not required.
`accepted_receipt_commit_failed` retains the original receipt/operation; recover it
without discovery or candidate substitution:

```powershell
python scripts/watch.py recover --operation OPERATION_ID
```

Already committed operations never submit again. Latest at/below handled progress is
not a new delivery; distinguish it from a new client's already_present acceptance.
A known total reached without confirmed finale evidence has target=null and reports
“等待完结确认”; completed records cannot be reopened by waiting or stale delivery.
Use [completion.md](completion.md) for independent finale reconcile and owning-task
cleanup; use [scheduled-new-anime.md](scheduled-new-anime.md) for schedule windows.
Window memory cannot replace v3 progress or count last week's handled episode as this
week's release without evidence.

## Migration and read-only boundaries

```powershell
python scripts/watch.py --state PATH migrate
python scripts/watch.py --state PATH migrate --apply --expected-sha256 PREVIEW_HASH
```

Preview is read-only. Apply rechecks the source hash under locks, preserves IDs,
bindings, progress/history, pending operations/downloads, aliases and evidence, saves
the old file backup and atomically writes v3. Conflicts/duplicates/orphan receipts are
rejected; obtain a fresh preview after source changes. Mutating v3 commands can perform
the same guarded migration automatically; inspect/discover/review do not migrate.

The old state editor rejects v3 writes. Do not use airing_watch_state.py update,
record-found, delete or legacy migration as the current workflow. Compatibility
`--no-state-update` cannot enqueue; use watch review for a read-only audit. Outbox and
reconcile are lifecycle mutations, not read-only inspection. Migration/maintenance
never changes an app schedule. See [architecture-v3.md](architecture-v3.md).
