# v3 architecture and acceptance

The repository is the local transaction boundary. JSON is written atomically under
a state lock and each track also has a deterministic identity lock. A command checks
the track revision before applying one domain change. State and outbox are serialized
in the same atomic write.

## State model

The v3 document has one identity, broadcast evidence, progress, lifecycle, delivery
receipts, operation ledger and outbox. `watched_episode`, `next_episode`, `airing`,
`status` and `tracking_status` are not v3 write fields. `next_episode` is derived from
`target_episode`. A known total reached without trusted finale evidence becomes
`finale_pending_evidence` with no target and the report says “等待完结确认”. A due
schedule with an undelivered finale keeps the final episode deliverable. Conflicting
evidence enters `blocked` while accepted progress is preserved.

## Pivot and recovery

`record_pending_operation` stores exact `track_id + operation_id + info_hash`, the
identity revision, review digest and request before the client call. The client must
return `already_present`, `submitted` or `submitted_verified` with matching receipt
fields. Acceptance is recorded before progress is committed. If a process dies
between those writes, `recover` inspects the original hash and commits the existing
receipt or an `already_present` result; it never searches or substitutes a candidate.

Desktop context failures and Web API failures use typed RecoveryAction. The Web API
adapter logs in when configured, checks exact hashes, supports magnet/torrent-file
adds and keeps a successful add accepted even if follow-up inspection is unavailable.

## Outbox and cleanup

A delivery adds a reconcile action atomically. Confirmed finale evidence can later add
cleanup only after exact automation ID, scope hash, all target tracks, accepted final
receipts and no pending operations are verified. The worker is at-least-once and
idempotent by action ID; it never submits torrents. Scheduler deletion goes through an
adapter and a successful receipt. Scope, target, retry-child or ID changes leave the
action pending.

## Migration

Migration is previewable and apply requires the preview SHA-256. It locks, fsyncs a
content-addressed `.v2.bak`, preserves track IDs/provider bindings/aliases/evidence,
receipts/operations/pending downloads and atomically replaces the file. Duplicate
tracks, season conflicts, illegal progress, conflicting hashes and orphan receipts
are rejected. Accepted receipts become committed; accepted-but-uncommitted operations
remain recoverable.

## Acceptance

The suite covers delayed finale evidence, pivot recovery, exact-hash adapters, cleanup
replay and failure, multi-target ownership, migration, old-writer rejection and
same/different-track concurrency. Run `pytest -q -p no:cacheprovider`.

## Temporary evidence lifecycle

`evidence_artifacts.py` owns indexed files below the tracking state's
`.cache/evidence` directory. `workspace` creates one UUID run per retrieval;
relative/root-Download output filenames are redirected to managed scratch space.
The CLI reports the actual output path. Successful delivery and recovery clean
owned evidence; failure retains uncommitted-operation references. Ended runs can
explicitly `cleanup --run`; unreferenced 48-hour-old files are swept on later runs.
Cleanup failures never change a delivery receipt or progress. State, committed
attestations, external files, locks and downloaded media are outside this collector.

## Scheduled new-anime template

Creation and execution use [scheduled-new-anime.md](scheduled-new-anime.md). The prompt
pins verified scope, original schedule and quality policy; actual app ID and saved
prompt SHA-256 are bound after creation. Runtime memory holds only schedule windows,
attempts and external-update intents; progress stays in v3. The read-only
scheduled_watch.py planner enforces four-hour same-task retries capped at three and
requires durable intent plus current configuration before preparing an app update.
Read-back verification handles a lost tool response without creating a second task.
Completed/pending-cleanup tracks route to outbox, not new discovery. Updating the
template does not automatically rewrite existing schedules.
