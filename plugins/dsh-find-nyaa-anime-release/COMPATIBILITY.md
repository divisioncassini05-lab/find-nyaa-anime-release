# Compatibility notes

## Verified contract

The adapter targets DeepSeek Harness `0.2.2-rc.1`, with reference source commit
`fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159`. It uses a Host-only bundle,
`dsh.bundle.patch`, the `skills` service and its `registerProvider` lifecycle.
The registered resource directory is derived from `import.meta.url`; there is no
assumption about a user's home path, install location or current chat directory.

Official sources:

- [Host plugin contract](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/preset/agent-preset/skills/cordis-plugin-development/references/host-plugin.md)
- [Skill registry](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/skill/skill/src/index.ts)
- [Schedule tools](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/schedule/tool-schedule/README.md)
- [Schedule rule contract](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/docs/subsystems/schedule.md)
- [Plugin index format](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/docs/user/guide/plugin-market.md)

`engines.dsh` is top-level under `engines`, not under `dsh`. The range is a
compatibility declaration, not a guarantee about unreleased versions. No core
service, terminal, browser, scheduler or model is force-installed by the bundle.

## Adaptations

| Surface | DSH behavior |
| --- | --- |
| Discovery | Native skill provider with lazy body loading and directory resourceBase |
| Commands | Packaged Python scripts, executed through the host's terminal approvals |
| State | Per-user DSH data directory; never auto-adopt Codex or publisher records |
| Client | Original audited delivery capability; portable paths, explicit Web API for remote use |
| Schedules | Native schedule tools; no Codex automation_update/heartbeat/thread IDs |
| Ownership | Complete live tool JSON converted into read-only v3 inventory/binding evidence |
| Cleanup | Missing/stale/partial inventory blocks deletion; exact-ID delete plus readback required |
| Retry | Native full DTSTART + RRULE and expectedUpdatedAt, with existing bounded weekly planner |
| Updates | Payload immutable; user state and pending operations stay outside node_modules |

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

This initial package has not been installed into a logged-in DSH desktop session;
there is no claim of GUI screenshot verification, live scheduled execution,
model-quality parity or actual qBittorrent download testing. Windows is the build
host; macOS/Linux data paths are unit-tested, not real-desktop launch tested. Python
3.11 is the supported minimum; this build is tested with the available local Python.
