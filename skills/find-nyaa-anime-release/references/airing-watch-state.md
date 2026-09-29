# Tracking identity and state

Read before state changes or interpreting a latest/next boundary. The state belongs
only to this skill; never synchronize desktop-app state, configuration or caches.
`runtime_paths.py` selects the existing Windows tracking file, otherwise the user's
Downloads directory. `ANIME_TRACKING_STATE` and `--state` override that location.

## Identity comes before progress

Explicit work/season/episode → unique current local match → other local records →
external discovery. `re0` and registered translations therefore select the current
tracked installment, not the first season returned by a provider. Multiple current
matches are a genuine ambiguity. An explicit other season never inherits the old
season's progress. Search-title variants aid retrieval, not record equivalence.

Every v2 record has its own `track_id`, `revision` and `identity_revision`. Provider
IDs are repairable bindings, never primary keys. Shared aliases/IDs never authorize
deletion, deduplication or merging. Reports project the legacy fields alongside
`work_identity.track_id`, stage records and binding-repair evidence.

The high-level workflow locks `WorkIdentity`. Metadata, cache, search results and
downloads cannot replace it. On a binding conflict the program searches that same
installment once. Repair needs the provider's own work/season/part/type evidence and
an independent provider or reviewed official page. Scores, airing status, total
episodes and discovered releases do not establish equivalence. Whole-season versus
split-part provider entries are not interchangeable. Ambiguity returns a conflict;
read-only runs return repair proposals without saving them.

## State commands and delivery

The repository is the only state writer. Operations explicitly create a track,
record waiting, save broadcast evidence, repair a binding, journal delivery, mark
delivered completion, or apply an intentional manual edit/removal. Updates address
`track_id`; per-work locks and identity revision checks protect finalization. The
existing qBittorrent profile lock and exact-hash check still serialize client sends.

Prepared operations are saved before client handoff. Accepted receipts are saved
before progress commit. `accepted_state_commit_failed` is not success: preserve the
receipt and rerun the same verified hash for client reinspection, never blindly
advance progress or substitute a different candidate. A launcher exit is not client
acceptance. Accepted magnets count as handled; downloading need not finish.

Only a qualified integer regular-episode magnet delivered to the user, verified
client acceptance, or an explicit manual operation can advance handled progress.
`watched_episode` retains this user's delivery-counts-as-handled meaning. Movie,
batch, special, decimal episode, unqualified/discovery-only result and failed client
handoff do not advance it. Latest at/below handled progress skips the client and is
`latest_already_handled`, not `already_present`. Explicit old-episode retrieval
leaves tracking state unchanged. Stale searches cannot regress progress or reopen
completed records.

Only confirmed current TV/TV_SHORT/ONA work can start tracking automatically.
Completed tracks are retained. A confirmed finale is targeted under the same quality
and subtitle constraints; completion requires its delivery, not merely its date.
Read [completion.md](completion.md) for official attestations, split-cour boundaries
and cleanup of the owning automation after persisted completion. Do not change a
scheduler during maintenance migration/deployment.

`--no-state-update` prohibits tracking writes AND client submission, even if enqueue
was also supplied. Disposable evidence/RSS caches may still be written. A probe
or v1 read does not migrate the state file.

## Commands

For an intentional scope edit to an existing record, use `update TITLE --track-id
ID_FROM_PROBE` with the desired fields. A title-plus-new-season lookup can otherwise
create a separate row. The ID does not authorize changing a work to fit a candidate.
The reviewed-release path keeps source numbering separate and normally needs no
local season edit.

```powershell
python scripts/airing_watch_state.py probe "TITLE"
python scripts/airing_watch_state.py get "TITLE"
python scripts/airing_watch_state.py record-found "TITLE" --episode 4
python scripts/airing_watch_state.py update "TITLE" --season S04 --watched 4
python scripts/airing_watch_state.py delete "TITLE"
python scripts/migrate_tracking_state.py --state PATH --preview
python scripts/migrate_tracking_state.py --state PATH --apply --expected-sha256 PREVIEW_HASH
```

`record-found` is an explicit manual/verified-delivery operation, not a discovery
shortcut. It does not create unknown tracks. Automated finalization must use the
high-level command, which performs candidate review, identity, constraints, client
acceptance and state submission together.

Migration applies only during a quiet writer window: lock, verify preview hash,
exclusive backup, assign independent IDs, preserve all rows/progress/completion,
mark historical bindings pending verification and atomically replace the JSON.
No alias-based deduplication. A changed preview hash requires a new preview.
See [architecture-v2.md](architecture-v2.md) for internal contracts and maintenance.
