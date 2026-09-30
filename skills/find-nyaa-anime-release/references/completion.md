# v3 completion evidence and owning-automation cleanup

Use this when the final episode may have aired, delivery preceded completion
confirmation, or a completed track still has pending cleanup. Scheduled creation
and bounded same-task retries use [scheduled-new-anime.md](scheduled-new-anime.md).

## Confirm the exact finale independently

Inspect the official work site or broadcaster episode/dated announcement page.
Match the immutable work/season/part/provider binding; distinguish a split-cour
break from completion of the requested scope. An expected end date, missing next
airing metadata, week counting, Nyaa absence or reaching an estimated total cannot
establish completion. Search snippets alone are insufficient.

Save a reviewed attestation under the managed run directory. It contains:

- `reviewed:true`, `confirmed:true`, positive integer `final_episode`.
- Actual `track_id` and current `identity_revision`, matching `season` and `part`
  (including null for unknown values). Read these from the repository; do not guess.
- Any supplied `anilist_id` / `bangumi_id` must match the immutable provider binding.
- `source_kind:official` or `broadcaster`, HTTPS `source_url`, exact supporting
  `evidence_text`, and the actual timezone-aware `checked_at`.
- Optional `end_date` (YYYY, YYYY-MM or YYYY-MM-DD), never a future completed date.
  Explain late-night dates and preserve the source's original broadcast-day label.

The v3 attestation validator requires confirmed evidence. A merely planned/revised
schedule is not passed to `reconcile --completion-evidence`; report/cache it as
unconfirmed metadata. Do not fabricate a confirmation to fit the interface.

## Reconcile without searching or submitting

```powershell
python scripts/watch.py reconcile "TITLE" --completion-evidence "RUN_DIR/COMPLETION.json"
python scripts/watch.py reconcile "TITLE"
python scripts/watch.py outbox --track-id TRACK_ID
```

The second form reevaluates evidence already stored. All writes go through
StateRepository. `reconcile` does not search or call qBittorrent; it is a mutating
lifecycle command, not a `--no-state-update` audit. For a read-only request inspect
state and evidence without attaching or reconciling it.

- Confirmed finale plus `progress.handled_episode >= final_episode` atomically
  sets `lifecycle.phase=completed`, clears `progress.target_episode`, preserves
  attestation/history and queues eligible automation cleanup.
- Final delivery can precede the attestation: later reconcile completes it without
  another download. If already completed, drain outstanding outbox actions.
- If the finale remains undelivered, preserve its pending delivery target and use
  the reviewed delivery workflow with the same quality rules. A scheduled end date
  cannot block that delivery. An exact-finale retrieval must not be mislabeled as
  broad evidence of Nyaa latest; use a specific-episode review if appropriate.
- When handled reaches known total without confirmed finale evidence, report
  `finale_pending_evidence` and “等待完结确认”; target is null. Do not invent episode 14.
- Conflicting final counts/identity require resolution; preserve progress and stop
  retrieval while blocked. Do not force an old flag to completed.

Client acceptance is sufficient; completion of the video download is not required.
Do not write legacy status/airing/watched/next fields or use `--mark-finished`.

## Bind real ownership before scheduled delivery

Obtain the exact Automation ID from the app result/run context. Read its complete
current prompt, exact saved configuration and all resolved targets. No title-only
or memory-only ownership inference. Hash the final prompt's UTF-8 bytes with SHA-256;
changing only rrule does not change this hash. Review a changed prompt before any
rebind, including unrelated work or explicit future-sequel monitoring.

Create an OWNER.json in the managed run directory containing these fields:

- `automation_id`: exact returned/current ID.
- `scope_hash`: SHA-256 of the complete saved prompt.
- `target_track_ids`: all exact targets covered by that prompt.
- `cleanup_policy`: `delete_when_all_targets_completed`.
- `scope_reviewed:true`, `all_targets_resolved:true` after actual review.
- `pending_retry_children`: verified pending children; new templates create none.
- `retry_children_checked_at`: actual timezone-aware inspection timestamp.

```powershell
python scripts/watch.py bind-automation --owner "RUN_DIR/OWNER.json" --automation-config "EXACT_AUTOMATION_TOML"
```

The configuration file is read-only evidence, not a scheduler edit interface.
Do not pass a made-up config or assume a successful create proves binding. A binding
failure must be reported and repaired before first delivery.

For legacy children, inspect each candidate's own parent/child declarations and run
evidence. Copied mentions of a parent's ID or `retry_child=true` are not ownership;
ACTIVE or COUNT=1 does not prove the child has not run. A pending child blocks parent
cleanup until its exact ownership and authorized cancellation are resolved.

## Execute and acknowledge deletion

This user's default is deletion, with completed records retained. Explicit retention
or read-only requests override it. No deletion until all scoped tracks are completed,
all final episodes have matching accepted receipts, no uncommitted delivery remains,
and no pending retry child or unfinished extra scope remains. Check current exact ID,
prompt hash and targets again immediately before the external action.

`watch outbox` reports `cleanup_pending` / `required_tool=automation_update` when the
host action has not run. That is not successful deletion. Use the app's
`automation_update` with mode delete and that exact ID; never erase scheduler files
or substitute PAUSED. If the tool response is uncertain, read back the exact ID.
A confirmed absent task can be acknowledged as already_absent; tool errors cannot.

Save the action/ownership information before deletion if memory may be removed.
Build a receipt using the actual tool result: automation_id, scope_hash and status
`deleted` or `already_absent`. Persist it in v3:

```powershell
python scripts/watch.py ack-outbox --track-id TRACK_ID --outbox-id OUTBOX_ID --receipt "RUN_DIR/CLEANUP_RECEIPT.json"
```

Keep the completed record and outbox receipt. Do not recreate a deleted automation's
memory directory. Deletion failure leaves cleanup_pending; later runs only retry
cleanup, with no torrent submission. If deletion succeeded but acknowledgement
failed, recover by verifying absence and acknowledging the same outbox ID.

Register temporary owner/attestation/receipt files with evidence_artifacts.register
when created outside an evidence CLI, and close the run after durable acknowledgement.
Never clean the only unpersisted receipt needed to recover an external action.
