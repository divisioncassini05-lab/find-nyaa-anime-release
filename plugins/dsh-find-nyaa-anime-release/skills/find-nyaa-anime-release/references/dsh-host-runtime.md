# DSH host integration

This reference owns host compatibility. The release rules and review/capability
gates are unchanged. Use DSH's available terminal and file tools; resolve relative
paths from the skill resource directory returned by the registry. Python is an
external prerequisite, not DSH's JavaScript interpreter. Do not call Codex APIs,
alter another host's records or install Python/qBittorrent without user approval.

## Data and download client

Run `python scripts/dsh_doctor.py` once on setup. Windows data defaults to
`%LOCALAPPDATA%/DSH/AnimeRelease`, macOS to
`~/Library/Application Support/DSH/AnimeRelease`, Linux to
`${XDG_DATA_HOME:-~/.local/share}/dsh/anime-release`.
`ANIME_DSH_HOME` selects a different absolute directory. The default is for one DSH
profile. Multiple scheduling profiles must use separate directories: a profile's
task inventory cannot prove another profile has no tasks. Do not share the state
between independent schedulers. Updates/uninstallation do not remove user data.

The default desktop download directory is `~/Downloads/Anime`, overridden by
`ANIME_DSH_DOWNLOAD_DIR` or the existing explicit CLI flag. Never import the
publisher's Windows directory or `ANIME_TRACKING_STATE`. Explicit `--state PATH`
still works, but sharing another installation's state requires user authorization.
The desktop launcher is Windows-oriented; for macOS, Linux, remote Hosts or
containers, prefer an explicitly configured `--client webapi --qb-url URL`.
Pass these flags consistently to delivery and recovery. A remote client's save
path belongs to that remote host: use its explicit directory, not a local path.
Credentials remain in QBITTORRENT_USERNAME/PASSWORD on the executing host, never
in prompts, task payloads, archives or command arguments. No Web API is enabled
automatically. Python may need `tzdata` on Windows for scheduler zone conversion.

## Native scheduler tools

DSH 0.2.2-rc.1 provides `schedule_create`, `schedule_list`, `schedule_view` and
`schedule_edit` in suitable presets. Discover their actual schemas. If unavailable,
continue interactive search and explain that scheduling/automatic owner cleanup
requires them; do not invent cron jobs or bypass the preset through storage files.
Delegated subagents cannot manage schedules. The plugin does not add those powers.

Changes use the exact current ID and `expectedUpdatedAt` from fresh readback.
`schedule_edit(action=delete)` really deletes; pause/ended/permission errors are not
absence. `schedule_not_found` for that exact ID is the only not-found acknowledgement.
On conflict re-read and review the change, never retry without the revision guard.
Keep prompt/target/preset intact for a timing-only edit. Use `this_session` by default
for creation; creating `new_once` again reserves a different session.

## Scheduler evidence bridge

The v3 verifier accepts a binding TOML and an inventory, while DSH returns JSON.
The bridge writes **derived local evidence**, never DSH configuration files.
Never type a substitute task based on memory: copy the actual tool object unchanged.

1. Call unfiltered `schedule_list` (omit `active`) and all its pages. Save:
   `{"observed_at":"ACTUAL_ISO_TIME","unfiltered":true,"pages":[ACTUAL_PAGE,...]}`.
   `observed_at` is the time of the first read in this observation, not an invented
   future time or a refreshed label on old data. Use a managed run directory.
2. Run `python scripts/dsh_host.py import-inventory --input "RUN_DIR/PAGES.json"`.
   It requires complete pagination, consistent totals and no duplicate task IDs.
   Failure invalidates the current snapshot instead of treating errors as no tasks.
3. For the exact task, call `schedule_view`. Save
   `{"observed_at":"ACTUAL_ISO_TIME","task":ACTUAL_TOOL_OBJECT}` and run:

```sh
python scripts/dsh_host.py task-snapshot --input "RUN_DIR/TASK.json" --output "RUN_DIR/SNAPSHOT.json" --toml "RUN_DIR/OWNER_CONFIG.toml"
```

The result supplies the exact UTF-8 prompt hash, derived binding config and durable
memory directory. Use OWNER_CONFIG.toml with `watch.py bind-automation` after
reviewing every real target and possible retry child. ID mention alone is not
ownership. Unrelated tasks are retained in inventory so they can block unsafe cleanup.

Refresh the full list immediately before completion/finalization and **after** any
schedule creation/edit/deletion; snapshots expire after 120 seconds. A missing,
partial, failed or expired inventory blocks local record removal. It never means
all schedules are gone. On delete, save the genuine tool receipt, refresh inventory,
then acknowledge the same outbox ID. Returned `required_tool=schedule_edit` is a
request for the Agent to act, not a claim that Python performed deletion.

## Retry rules

The existing planner handles only one weekly time in Asia/Shanghai, with at most
three four-hour retries. Other DSH timing kinds or zones keep the saved schedule
without this automatic retry optimization; report that limit, never reinterpret
their times. Task snapshots mark `retry_supported` explicitly. Memory lives under
the returned `memory_directory/memory.md`, not Codex automation storage.

For supported tasks, SNAPSHOT.json normalizes active/paused/ended and a weekly
rule for `scheduled_watch.py plan/prepare/verify`. Save the plan and read it back
as the durable intent before editing. After `prepare`, use:

```sh
python scripts/dsh_host.py retry-edit --plan "RUN_DIR/PLAN.json" --snapshot "RUN_DIR/SNAPSHOT.json" --saved-intent "RUN_DIR/SAVED_INTENT.json"
```

This rechecks the intent, prompt hash, current rule, revision and snapshot freshness,
then supplies the full DTSTART + RRULE and guarded arguments for native schedule_edit.
Only call it when `update_required`. Read the actual DSH task back, recreate the
snapshot and run the existing `verify`; refresh inventory. No new retry child is
created. If DSH changed the rule, paused the task or rejects the update, stop and
report it. A scheduled message/lastDelivery is trigger evidence, not current time,
release publication, successful execution or qBittorrent acceptance.
