# Broadcast end dates and delivered finales

Use this for automatic latest runs, tracked-next, a known final episode, missing or
conflicting metadata, and correcting an obsolete airing record.

The resolver requests AniList `endDate`, status and episode total, preserving year,
month or day precision. `completion` in snapshots, state and reports carries the
date, confirmation, final episode, source URL and check timestamp. An expected date
passing triggers review; it does not establish actual completion or a Nyaa release.
A year/month deadline becomes overdue only at the end of that year/month.

When `needs_completion_review` is returned, or metadata is unavailable, overdue,
missing at a season boundary or contradictory, use the web tool to inspect the work's
official site or broadcaster episode page. Confirm the exact work/season and whether
the episode is explicitly the finale. Read the page itself; search snippets, an absent
next-airing field, and counting weeks from the premiere are insufficient evidence.
Record planned dates as `confirmed:false`; use `confirmed:true` only for broadcasting
that has actually ended. If sources disagree, check dated postponement/finale notices;
do not resolve the conflict by silently picking a date. If unresolved, keep progress
and report the uncertainty. Refresh the ordinary metadata cache after a postponement.

Pass Agent-reviewed official evidence through `--completion-evidence PATH` on the
same high-level request, first with `--no-state-update` when auditing. Example:

```json
{
  "anilist_id": 190569,
  "bangumi_id": 552533,
  "season": "S01",
  "reviewed": true,
  "confirmed": true,
  "final_episode": 12,
  "end_date": "2026-09-12",
  "source_kind": "broadcaster",
  "source_url": "https://www.bs-asahi.co.jp/anime-jaadugar/lineup/prg_012/",
  "evidence_text": "第12幕（最終回）; the page labels its broadcast date September 12.",
  "checked_at": "2026-09-20T11:00:00+00:00"
}
```

Use the actual inspection timestamp. At least one known numeric work ID must match;
all supplied known IDs and the exact SNN season must agree. Source kinds are `official`
or `broadcaster`. HTTPS source, supporting text and timezone-aware timestamp are required.
This is a local Agent attestation interface, not an automatic arbitrary-page verifier.
`end_date` accepts YYYY, YYYY-MM, YYYY-MM-DD or null; retain the broadcaster's original
broadcast-day label and explain late-night/rebroadcast conventions in evidence text.
The confirmed finale is sufficient even when its exact end date is unavailable.
For reviewed revised schedules use `confirmed:false` and the revised planned date.

For a confirmed finished season with an undelivered finale, the automatic resolver
targets the final regular episode explicitly. It still verifies size, subtitles,
identity and the pinned candidate, then requires successful client acceptance in
download mode. Do not call this exact-finale search a broad proof of Nyaa latest.
Failures do not advance watched progress. Successful final delivery retains the show
with `status=completed`, `tracking_status=completed`, `airing=false`, `next_episode=null`.
Completed records short-circuit future latest/next checks without network or client calls.
An explicit old episode remains a retrieval-only request. `--no-state-update` performs
no tracking-state writes. Marking completion never proves download completion.

## Delete completed tracking automations

This user's preference is to delete a finished tracking automation, not pause it.
The resolver writes watch state; it cannot delete a Codex scheduler entry by itself.
The Agent must finish this separate cleanup after delivery, including when a later
run discovers a previously persisted completed record.

JSON reports expose `automation_cleanup.action=delete_owning_automation` when all
reported shows have persisted completed delivery. This is an advisory with
`executed=false`, not proof of scheduler deletion or authorization to delete a task
whose prompt includes additional unreported work. Read-only audits return `keep`.

1. Resolve the owning Automation ID and inspect its current prompt/scope. Do not infer
   ownership from a title match alone or touch another automation for the same show.
2. Confirm that the final episode has been delivered and the local record is persisted
   as `completed` with `next_episode=null`. Discovery, a broadcast date, failed enqueue,
   and `--no-state-update` audit output alone do not qualify. Client acceptance is enough;
   do not wait for video download completion. Retain the completed watch record.
3. For a single-show automation, call the app's `automation_update` with `mode=delete`
   and that exact ID. For a multi-show automation, check every show named by its prompt:
   keep the task if any is unresolved, airing, awaiting delivery, or at a split-cour break;
   delete it only after all requested targets are complete. Preserve explicit future
   sequel-monitoring instructions; do not equate a season finale with that scope finishing.
4. Save a concise completion/cleanup record before deletion if deletion may remove its
   memory directory. Require a successful delete response before saying it was deleted.
   If deletion fails, report `automation_cleanup_failed` and the reason; do not silently
   substitute PAUSED or change scheduler configuration through filesystem writes.

An explicit user instruction to retain/pause a particular task overrides this default.
Normal download runs must leave other shows and unrelated automations alone.

## Completion takes precedence over ordinary retry handling

Check terminal delivery at both entry (persisted completion) and after a successful
commit. A completed track has no missing next episode: do not route it to resource
search, a no-new-release retry, or an ordinary success branch that retains the parent.
The resolver's `executed=false` means scheduler work remains for the Agent. A run
may report the finale delivered while cleanup is pending/failed, but must not imply
the recurring task stopped until the app confirms deletion. On a later run, resume
cleanup from the completed record without re-submitting the torrent.

For new or explicitly authorized repairs to scheduled prompts, scope parent
protection to ordinary retries: preserve the parent while its requested work is
unfinished; once all requested finales are confirmed, accepted and persisted, delete
the owning parent and its confirmed pending retry children through the app tool.
Include that terminal branch in child prompts as well. Never generate an
unconditional "never delete the parent" clause for this lifecycle.

Existing explicit retention instructions still require resolution against the
current user request. A request to fix this completion-cleanup failure authorizes
correcting the conflicting lifecycle for that task. Without that authorization,
report the conflict as pending cleanup instead of silently treating retention as
successful closure. Do not rewrite unrelated schedules or sequel-monitoring scope.

When enumerating children, parse saved UTF-8 TOML, exclude the exact parent ID,
and verify each candidate's own retry-child/parent/attempt declarations. Mentions
inside copied lifecycle instructions are not declarations: the parent often contains
the literal text `retry_child=true` itself. Do not identify ownership by substring
alone. Check run evidence before deleting a pending child; ACTIVE and COUNT=1 do not
prove it has not run. Preserve other running tasks. Save memory before deletion and
retain a workspace copy if deleting the task removes its memory directory; never
recreate a deleted automation directory just to write the final result.
