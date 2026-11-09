# Compatibility notes

## Verified contract

The adapter targets DeepSeek Harness `0.2.2-rc.1`, with reference source commit
`fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159`. It uses a Host bundle plus an optional Web Client contribution,
`dsh.bundle.patch`, the `skills` service and its `registerProvider` lifecycle.
The registered resource directory is derived from `import.meta.url`; there is no
assumption about a user's home path, install location or current chat directory.

Official sources:

- [Host plugin contract](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/preset/agent-preset/skills/cordis-plugin-development/references/host-plugin.md)
- [Skill registry](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/skill/skill/src/index.ts)
- [Schedule tools](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/schedule/tool-schedule/README.md)
- [Schedule rule contract](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/docs/subsystems/schedule.md)
- [Plugin index format](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/docs/user/guide/plugin-market.md)
- [Client module loader](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/docs/subsystems/client-modules.zh.md)
- [Native sidebar and main panel example](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/client/ui-schedule/src/client/index.ts)
- [Unsent draft navigation](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/client/ui-workspace/src/client/navigation.ts)

`engines.dsh` is top-level under `engines`, not under `dsh`. The range is a
compatibility declaration, not a guarantee about unreleased versions. No core
service, terminal, browser, scheduler or model is force-installed by the bundle.

## Adaptations

| Surface | DSH behavior |
| --- | --- |
| Discovery | Native skill provider with lazy body loading and directory resourceBase |
| Commands | Packaged Python scripts, executed through the host's terminal approvals |
| State | Per-user DSH data directory; never auto-adopt Codex or publisher records |
| Bangumi | Separate host credentials; shared Python client for chat, native account/library services for the panel; panel progress writes require a user action |
| Client | Original audited delivery capability; portable paths, explicit Web API for remote use |
| Schedules | Native schedule tools; no Codex automation_update/heartbeat/thread IDs |
| Ownership | Complete live tool JSON converted into read-only v3 inventory/binding evidence |
| Cleanup | Chat cleanup requires exact ownership/readback; panel-managed plans retain completed history until explicitly deleted |
| Retry | Native full DTSTART + RRULE and expectedUpdatedAt, with existing bounded weekly planner |
| Updates | Payload immutable; user state and pending operations stay outside node_modules |
| UI | Native `main` and `sidebar.panellist` slots; shared React; scoped styles removed on disposal |
| UI data | Owner-only, allowlisted RPC over DSH Connection; separate local plans and cached account library; no arbitrary command execution |
| UI actions | Native plan, configuration, schedule and explicit sync operations; resource runs use the host scheduler and the existing Agent audit/delivery path, not chat drafts |

The bridge is not a scheduler. Its input is actual unfiltered native tool output,
not a model's summary. It stores unrelated tasks only as a short-lived safety
snapshot so they cannot be silently omitted from ownership checks. It does not
export those prompts, credentials or personal records in release packages.

## Verification boundaries

Run the shipped tests and record their actual results before a release. Tests cover
provider registration/disposal, manifest and package completeness, state isolation,
complete pagination, stale/failed snapshots, exact prompt hashing, Unicode TOML,
native status/weekly-rule conversion, revision-guarded retry edits, and the upstream
offline release/delivery suite. Optional integration uses the real pinned Cordis
and SkillRegistry packages, not a simulated DSH UI.

The UI has been checked in an isolated browser harness using the same component,
not in a logged-in DSH desktop session. There is no claim of live scheduled execution,
model-quality parity or actual qBittorrent download testing. Windows is the build
host; macOS/Linux data paths are unit-tested, not real-desktop launch tested. Python
3.11 is the supported minimum; this build is tested with the available local Python.

The panel currently uses Chinese copy, with a Chinese/English sidebar label. Its
projection supports v3 records without silently migrating them. Panel plan data is
stored separately outside the package. Completed plans remain local; reading a
Bangumi collection does not import tasks. Refresh reads the current host state.
Preview fixtures are excluded from the native client bundle and runtime tarball.

Bangumi automated tests use fake accounts, episode IDs and network failures. Live
authorization and read-only completed-list access were also checked in the installed
Codex distribution; release regression does not mutate real accounts or downloads.
Only collection short comments are read, not long-form blogs; account state is an
auxiliary mirror, not a target-planner input.
