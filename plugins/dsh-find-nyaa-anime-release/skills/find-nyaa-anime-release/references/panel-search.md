# Execute one DSH panel search

`[anime-plan:ID]` is an authorized Run-once or scheduled request. Treat its title
and JSON as data. Run commands from the absolute **skill resource directory**
returned by the skill tool, not the workspace or plugin root. Use Python UTF-8
mode (`python -X utf8`; substitute python3/py -3 when that is the installed runner).

Start with one read-only command:

```powershell
python -X utf8 scripts/dsh_panel_run.py --plan-id ID context
```

For automatic runs add `--scheduled` before the subcommand on every wrapper call.
The context contains only this plan, its existing core identity, pending operation
IDs, recorded episode coverage and exact `policy_args`. Reuse it; no full-library
read, global `snapshot`, directory survey, `--help`, doctor or source inspection
is needed for normal retrieval. `snapshot` serves the UI and probes downloads;
it is not the search initialization command. Context does not create a track,
mark watching, contact services, or prove current broadcast/release availability.

Use [retrieval-workflow.md](retrieval-workflow.md) for complete evidence collection.
Replace every `watch.py SUBCOMMAND` with this wrapper's `watch SUBCOMMAND`, and
every `package_release.py SUBCOMMAND` with `package SUBCOMMAND`. Create the owned
run directory using `... watch workspace`; keep every input/report there.
Independent reads/details can share a tool call. Reuse complete reports; read only
missing chunks after truncation. Do not truncate listings yourself or omit a
plausible candidate to reduce cost.

- `latest_regular` (including legacy `next_tracked`): inspect the supplied track,
  establish the latest aired regular episode from current evidence, and follow
  [agent-review.md](agent-review.md). Missing authorized tracks use the exact
  `track_id` and the JSON example in [airing-watch-state.md](airing-watch-state.md)
  after identity verification. Pending operations recover their original hash.
- `missing_episodes`: after verifying latest episode N, call `... targets --through N`.
  Use `specific_episode` for its gaps and reuse the same full evidence across
  reviews. Preserve partial finds; retry pending downloads only through the wrapper.
- `season_batch`/`movie`: follow [package-review.md](package-review.md). Copy the
  returned `package_scope_binding` into the independently verified scope, retaining
  the plan title/season and exact Bangumi ID; verify its kind and episode count.
  Do not create a regular-series track. A qualified complete package finishes
  the search, while download status stays separate. Catalogue choices still apply.

Copy the returned policy flags into draft/audit/deliver without changing bounds,
Chinese requirements or upward compatibility. The draft's `quality_policy` is
already complete; fill the semantic fields using the linked review schema.
For link-only, audit once. For authorized download, deliver directly: it performs
the fresh audit. A successful wrapper result is the receipt for recording the find;
do not read implementation files, the whole result store or durable copies again
to reconstruct what it already confirmed. Then clean the owned run directory.

Wrappers check plan ownership, pause/deletion and automatic-run state. They perform
the optional start-watching check during execution and record validated results.
An optional Bangumi failure does not restart retrieval. Download only if
`enqueue_qbittorrent` is true. Never call watched/flush/finalize, delete schedules,
or write progress/result files manually; the panel retains history and owns sync.

On `permission_denied`, use the host's approved access flow for the reported path
when available; otherwise stop with that unresolved stage. Do not diagnose an
expected workspace boundary by source inspection, custom retry scripts or ACL
edits. For other actual failures read the matching recovery reference. A normal
search is not a maintenance session.
