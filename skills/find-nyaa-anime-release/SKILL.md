---
name: find-nyaa-anime-release
description: Find and verify Nyaa anime releases with Agent-reviewed work, season, episode, and movie identity; soft Chinese-subtitle preference unless explicitly required; hard quality and size checks; verified magnets; automatic qBittorrent enqueue for scheduled bare-title runs; and monotonic current-anime tracking. Use for latest, specific, tracked-next, movie, whole-season, subtitle, magnet, progress, and scheduled-download requests. Non-download discovery is read-only. Default floors are 1 GiB per regular episode and 10 GiB per movie.
---

# Find Nyaa Anime Release

Use the deterministic scripts to collect and verify evidence; use Agent judgment to decide the actual work, branch, season, release type, episode, and final candidate. Return only releases the user is legally entitled to access.

Run commands from this skill directory. Use these entrypoints:

| Task | Entrypoint |
| --- | --- |
| Read local progress | `airing_watch_state.py probe` |
| Discover titles and compare release candidates | `search_nyaa_releases.py --discover` (read-only, no magnets) |
| Resolve episodic metadata or check latest/next/whole-season | `find_anime_release.py --no-state-update` |
| Finalize a reviewed episode, including enqueue and eligible tracking | `find_anime_release.py --candidate-id ID` |
| Discover/verify a movie, using total-size bounds | `search_nyaa_releases.py --movie`; no tracking-state writes |

Start an exact-episode discovery with independently verified search titles:

```powershell
python scripts/search_nyaa_releases.py "VERIFIED TITLE" --season S01 --episode 4 --tier browse --want-zh --discover
```

## Request routing

Always run a read-only local-state probe before an ordinary title search:

```powershell
python scripts/airing_watch_state.py probe "USER TITLE"
```

- Explicit episode, “下一集”, latest, movie, whole-season, quality, size, source, group, and subtitle wording override defaults.
- A bare tracked title means its next episode interactively. “Latest already available” and a scheduled bare title mean the latest regular episode established by that run; incomplete discovery must not fall back to stored progress.
- A bare-title Codex cron/automation is automatic-download intent unless its prompt explicitly says check only, magnet only, or no download. First run read-only latest discovery and audit full candidate evidence. Then finalize with `--latest --candidate-id ID --include-magnet --legal-ok --enqueue-qbittorrent`; unreviewed enqueue returns `review_required` and does not contact the client.
- Tracking state is not an answer cache. For tracked works with verified search titles, use those titles as the ordinary Nyaa queries first. Never persist an alias learned only from a selected release.
- Use at most three broad, high-confidence queries. A CJK-only result cannot establish the latest episode; recover an independent Latin/romaji title and rerun the ordinary lane.
- Map `随便看看` to `browse`, `普通画质` to `watch`, and `高画质`/stronger wording to `premium`. The default hard floor is 1 GiB per regular episode; movies default to `--movie --min-total-gib 10`. Explicit bounds are hard.
- In unpinned high-level searches, named tiers may fall back once: `watch` → `browse`, or `premium` → `watch`. Explicit size bounds disable fallback. Hard-Chinese `watch` → `browse` requires confirmation. Label any downgrade; see the quality reference for whole-season upgrade offers. Pinned finalization never automatically changes tier.
- Enable `--allow-upward-compatibility` only when requested. It never relaxes a tier floor or explicit maximum.

Read [references/airing-watch-state.md](references/airing-watch-state.md) before a state write or difficult latest/next decision. Read [references/quality-ranking.md](references/quality-ranking.md) for tier fallback, batch math, source exemptions, or ranking disputes.
If discovery, verification, submission, or retry scheduling fails, read [references/failure-recovery.md](references/failure-recovery.md). Use the report's `recovery` guidance to select the next stage; it does not authorize a scheduled retry.

## Subtitle policy

There are exactly two normal modes:

- If the originating prompt explicitly requires Chinese, Simplified Chinese, or Traditional Chinese subtitles, pass `--require-zh`. Actual CHS/CHT, Chinese track, or subtitle-file evidence is mandatory; `MultiSub` alone is insufficient.
- Otherwise pass `--want-zh`. Chinese evidence is a same-quality tie-breaker only and its absence never disqualifies a release.

A Chinese title, UI language, tracking record, previous answer, or retry reason does not create a hard subtitle requirement. If ordinary discovery fails, the trustworthy Chinese-title supplemental exact-episode lane is mandatory before strict rejection; the Chinese lane is a supplement, not a replacement. If a genuine Simplified/Traditional pair is independently available, try both in the same supplemental call; a Japanese title containing kana is not a substitute. Do not manufacture or persist a Traditional alias merely to make a release discoverable.

Use `--trust-cjk-title-for-zh` only for an independently known Chinese title that exactly matches the work and episode. It skips subtitle detail inspection, so report title-based evidence accurately. An S01 title may omit the season marker, but never extend that inference to later seasons. For latest strict-Chinese requests, let the ordinary broad Latin/romaji discovery determine the latest regular episode before the Chinese exact-episode lane.

## Select and verify

Follow: discover → audit full titles → verify the selected ID → enqueue when requested or scheduled → update progress.

For latest, ambiguous parsing, or a diagnostic, read [references/retrieval-core-v2.md](references/retrieval-core-v2.md). Use the versioned `SearchRun`, identity, target and eligibility evidence together. The first two summary choices are not the full search: check counts/truncation and `search_run.raw_candidates` before claiming absence. Never turn a parser's score into a probability of correctness.

- Exclude previews, recaps, OVA/OAD, specials, movies, mini-series, and batches from regular-episode decisions. Never select the first row merely because it is first.
- Apply work, season, type, tier, size, source, group, and explicit subtitle constraints before ranking. Compare swarm health only among otherwise comparable releases; do not add a fixed seeder threshold.
- For an exact/latest episode, compare visible same-episode alternatives once and verify exactly one ID. Prefer a `--fast-verify` hint only after auditing it; on failure, try exactly one distinct backup candidate.
- Build a representative shortlist of up to 3–5 IDs only for real identity ambiguity, strict subtitle evidence, whole-season validation, conflicting parsing, or explicit alternatives.
- Pass the reviewed ID into high-level finalization with exactly one of `--episode N`, `--latest`, or `--whole-season`. `--latest` independently establishes the latest target before verifying the pinned ID; an older ID cannot redefine latest. A rejected ID is never replaced automatically. If a lower tier has already been accepted, explicitly pass that effective tier.
- Reuse the discovery query set for `--candidate-id` verification. Final verification always includes `--include-magnets --legal-ok`; never expose a magnet from an unqualified report.
- Movie checks use total size, never per-episode bounds. Whole-season checks require an authoritative episode count, file-list coverage, extras exclusion, and per-file quality; package total alone is insufficient.
- Ask the user only when a real work/version ambiguity changes the answer.

RSS/listing cache writes are disposable network caches, not tracking-state writes. Never declare a latest episode from a CJK-only discovery. Every pinned finalization reads `https://nyaa.si/view/ID` and rechecks identity and constraints, including when the ID already exists in cache; failed detail verification cannot fall back to the cached row.

For a read-only whole-season check:

```powershell
python scripts/find_anime_release.py "TITLE" --season S01 --whole-season --tier premium --want-zh --no-state-update --include-magnet --legal-ok --json
```

## Enqueue and tracking

Finalize the reviewed episodic candidate through the high-level resolver so the same ID is rechecked, submitted, and then recorded:

```powershell
python scripts/find_anime_release.py "USER TITLE" --search-title "VERIFIED TITLE" --season S01 --episode 4 --candidate-id 1234567 --tier browse --want-zh --include-magnet --legal-ok --enqueue-qbittorrent --json
```

For a scheduled latest run, replace `--episode 4` with `--latest` and keep the reviewed ID. For link-only delivery, omit `--enqueue-qbittorrent`. For a read-only verification, also pass `--no-state-update`.

Movies stay on the low-level path:

```powershell
python scripts/search_nyaa_releases.py "VERIFIED MOVIE TITLE" --movie --min-total-gib 10 --want-zh --discover
python scripts/search_nyaa_releases.py "VERIFIED MOVIE TITLE" --movie --min-total-gib 10 --want-zh --candidate-id 1234567 --include-magnets --legal-ok --report
```

If a movie download was requested, submit its verified magnet with `qbittorrent_submit.py`; movie delivery never updates episodic progress. The low-level movie command does not accept or need `--no-state-update`.

Accept only `already_present`, `submitted`, or `submitted_verified`. On failure, report the verified magnet and error without advancing state.

- For a scheduled bare title, enqueue exactly one qualified latest regular episode. Only an explicit check-only, magnet-only, or no-download instruction makes that run read-only.
- When the high-level resolver downloads, use `--enqueue-qbittorrent` so submission succeeds before its state write.
- The retired `--defer-state-until-download-complete` flag returns an error; remove it to use the standard delivery boundary below. Legacy pending records are cleared by a newer successful delivery.
- In link-only mode, advance progress only when a fully qualified magnet is actually returned. Metadata-only results do not advance progress. In automatic-download mode, advance only after qBittorrent returns `already_present`, `submitted`, or `submitted_verified`.
- A latest episode at or below stored progress is `latest_already_handled`: report the latest, current progress, and next target. Do not call qBittorrent for that scheduled latest run, and report `not_attempted`; stored progress is never evidence that a qBittorrent task or downloaded file currently exists.
- Classify tracked-next availability before searching: `not_aired_yet` means the normal scheduled time is still in the future; `availability.state = aired_no_release` means the target has aired but no qualified release was delivered; `airing_schedule_break` means an official same-series gap of 10.5–27.99 days; `long_break_unconfirmed` means a gap of 28 days or more without explicit split-cour evidence; and `split_cour_break` means the current part is finished and an official mainline sequel is explicitly named Part 2/2nd Cour. A completed part without that explicit evidence is `part_finished`. Report dates and evidence, never collapse these cases into “not found.”
- For `not_aired_yet`, schedule breaks, long breaks, and part boundaries, do not search Nyaa or update progress. Only call a long gap split-cour when official structured sequel metadata supports it; title resemblance alone is insufficient.
- Advance an already tracked show only for a verified, strictly newer integer regular episode. Older/same episodes are retrieval-only.
- Never update progress for discovery rows, failed candidates, missing magnets, movies, batches, specials, decimal episodes, or unresolved identity.
- A first qualified result may start tracking only for a confirmed current TV, TV_SHORT, or ONA. Confirmed current works with no qualifying release may become `tracked_waiting`; completed works and non-episodic releases remain stateless.
- Use `--no-state-update` for high-level metadata, batch, rescue, and unresolved checks. Low-level discovery and movie verification never write tracking state.

### First-search finalization for an untracked current anime

Finalize an untracked episodic work through `find_anime_release.py`, preserving the reviewed `--candidate-id`, discovered season, episode, tier, bounds, subtitle mode, and independently verified search titles. For an unsuccessful search with no reviewed candidate, omit `--candidate-id` when finalizing a confirmed current work as waiting. Do not replace this with a low-level `record-found` write. A qualified current work reports `state_update: advanced`; a confirmed current work with no qualified release may report `state_update: tracked_waiting`.

## Failure handling

Keep confirmed work, target, candidates and failed stage separate. A successful search followed by qBittorrent failure is `available_enqueue_failed`, never “not found” or `search_incomplete`. A partial query failure cannot prove absence or establish latest from an older surviving result.

Recovery is bounded: refresh a cached negative once if needed, use verified Chinese-title exact-episode supplementation, then the eligible official-date rescue. Preserve the target and constraints; do not rerun the entire enqueue command while its process is still running. Resume its returned session ID instead. See the failure reference for boundaries and stopping rules.

Keep both execution layers' handles when tools return early: resume the orchestration cell until it returns the command's `session_id`, then resume that command session. Empty output is not completion. Discovery may run in parallel; submit reviewed targets sequentially to the same client profile (the submitter also serializes cross-process handoffs).

After a client failure, inspect the local client and error first. `startup_exited_without_client` means the launcher exited but no client was detected; diagnose execution permissions/user context, not resource availability. An approved launch in the normal user environment may be required by the execution tools. Do not weaken sandbox settings or invent a timed retry to bypass a permission failure.

On Windows, execute the complete reviewed `find_anime_release.py ... --candidate-id ID --enqueue-qbittorrent` command through the execution tool's approved normal-user context when desktop launch requires it. This keeps metadata creation, client startup, handoff, acceptance checks and progress recording in the same context. Elevating only `Start-Process` and then returning to restricted submission does not complete this recovery. When prior memory records this failure, use the approval mechanism for the full command from the first submission; discovery stays read-only. This is a tool-permission request, not a new request for download intent. The script must never elevate itself.

`handoff_unverified` applies to both torrent-file and magnet submissions with no valid matching task record. Neither a launcher exit nor an empty `.fastresume` file is acceptance. Follow the client-recovery reference to verify the execution context before repeating a failed handoff.

## Final response

Compose from structured evidence. State the exact work/season/episode or movie, release title, size scope, seeders, upward compatibility if used, relevant subtitle evidence, and enqueue result. A recommendation includes its verified magnet in a plain-text code block.

For failure, distinguish not released, identity ambiguity, hard quality/size rejection, strict subtitle rejection, incomplete scan/detail inspection, network failure, and qBittorrent failure. If the latest episode exists but no release qualifies, report that episode and reason rather than returning an older one.
