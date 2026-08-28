---
name: find-nyaa-anime-release
description: Find and verify Nyaa anime releases with Agent-reviewed work, season, episode, and movie identity; soft Chinese-subtitle preference unless explicitly required; hard quality and size checks; verified magnets; automatic qBittorrent enqueue for scheduled bare-title runs; and monotonic current-anime tracking. Use for latest, specific, tracked-next, movie, whole-season, subtitle, magnet, progress, and scheduled-download requests. Non-download discovery is read-only. Default floors are 1 GiB per regular episode and 10 GiB per movie.
---

# Find Nyaa Anime Release

Use the deterministic scripts to collect and verify evidence; use Agent judgment to decide the actual work, branch, season, release type, episode, and final candidate. Return only releases the user is legally entitled to access.

Run commands from this skill directory. Prefer the high-level resolver:

```powershell
python scripts/find_anime_release.py "USER TITLE" --episode 4 --tier browse --want-zh --include-magnet --legal-ok --json
```

## Request routing

Always run a read-only local-state probe before an ordinary title search:

```powershell
python scripts/airing_watch_state.py probe "USER TITLE"
```

- Explicit episode, “下一集”, latest, movie, whole-season, quality, size, source, group, and subtitle wording override defaults.
- A bare tracked title means its next episode interactively. “Latest already available” and a scheduled bare title mean the latest regular episode established by that run; incomplete discovery must not fall back to stored progress.
- A bare-title Codex cron/automation is automatic-download intent unless its prompt explicitly says check only, magnet only, or no download. Use the high-level resolver with `--latest --include-magnet --legal-ok --enqueue-qbittorrent`; omitting enqueue is not a valid successful scheduled run.
- Tracking state is not an answer cache. For tracked works with verified search titles, use those titles as the ordinary Nyaa queries first. Never persist an alias learned only from a selected release.
- Use at most three broad, high-confidence queries. A CJK-only result cannot establish the latest episode; recover an independent Latin/romaji title and rerun the ordinary lane.
- Map `随便看看` to `browse`, `普通画质` to `watch`, and `高画质`/stronger wording to `premium`. The default hard floor is 1 GiB per regular episode; movies default to `--movie --min-total-gib 10`. Explicit bounds are hard.
- Enable `--allow-upward-compatibility` only when requested. It never relaxes a tier floor or explicit maximum.

Read [references/airing-watch-state.md](references/airing-watch-state.md) before a state write or difficult latest/next decision. Read [references/quality-ranking.md](references/quality-ranking.md) for tier fallback, batch math, source exemptions, or ranking disputes.

## Subtitle policy

There are exactly two normal modes:

- If the originating prompt explicitly requires Chinese, Simplified Chinese, or Traditional Chinese subtitles, pass `--require-zh`. Actual CHS/CHT, Chinese track, or subtitle-file evidence is mandatory; `MultiSub` alone is insufficient.
- Otherwise pass `--want-zh`. Chinese evidence is a same-quality tie-breaker only and its absence never disqualifies a release.

A Chinese title, UI language, tracking record, previous answer, or retry reason does not create a hard subtitle requirement. If ordinary discovery fails, the trustworthy Chinese-title supplemental exact-episode lane is mandatory before strict rejection; the Chinese lane is a supplement, not a replacement. If a genuine Simplified/Traditional pair is independently available, try both in the same supplemental call; a Japanese title containing kana is not a substitute. Do not manufacture or persist a Traditional alias merely to make a release discoverable.

Use `--trust-cjk-title-for-zh` only for an independently known Chinese title that exactly matches the work and episode. It skips subtitle detail inspection, so report title-based evidence accurately. An S01 title may omit the season marker, but never extend that inference to later seasons. For latest strict-Chinese requests, let the ordinary broad Latin/romaji discovery determine the latest regular episode before the Chinese exact-episode lane.

## Select and verify

Follow: discover → audit full titles → verify the selected ID → enqueue when requested or scheduled → update progress.

- Exclude previews, recaps, OVA/OAD, specials, movies, mini-series, and batches from regular-episode decisions. Never select the first row merely because it is first.
- Apply work, season, type, tier, size, source, group, and explicit subtitle constraints before ranking. Compare swarm health only among otherwise comparable releases; do not add a fixed seeder threshold.
- For an exact/latest episode, compare visible same-episode alternatives once and verify exactly one ID. Prefer a `--fast-verify` hint only after auditing it; on failure, try exactly one distinct backup candidate.
- Build a representative shortlist of up to 3–5 IDs only for real identity ambiguity, strict subtitle evidence, whole-season validation, conflicting parsing, or explicit alternatives.
- Reuse the discovery query set for `--candidate-id` verification. Final verification always includes `--include-magnets --legal-ok`; never expose a magnet from an unqualified report.
- Movie checks use total size, never per-episode bounds. Whole-season checks require an authoritative episode count, file-list coverage, extras exclusion, and per-file quality; package total alone is insufficient.
- Ask the user only when a real work/version ambiguity changes the answer.

RSS/listing cache writes are disposable network caches, not tracking-state writes. Never declare a latest episode from a CJK-only discovery. If the selected ID is absent from cached discovery, the verifier reads `https://nyaa.si/view/ID` directly and rechecks its evidence.

For a read-only whole-season check:

```powershell
python scripts/find_anime_release.py "TITLE" --season S01 --whole-season --tier premium --want-zh --no-state-update --include-magnet --legal-ok --json
```

## Enqueue and tracking

Only enqueue after exact verification, and enqueue exactly one qualified release:

```powershell
python scripts/qbittorrent_submit.py "MAGNET" --source-url "NYAA_PAGE_URL" --save-path "C:\User_data\Download\qBittorrent" --json
```

Accept only `already_present`, `submitted`, or `submitted_verified`. On failure, report the verified magnet and error without advancing state.

- For a scheduled bare title, enqueue exactly one qualified latest regular episode. Only an explicit check-only, magnet-only, or no-download instruction makes that run read-only.
- When the high-level resolver downloads, use `--enqueue-qbittorrent` so submission succeeds before its state write.
- In link-only mode, advance progress only when a fully qualified magnet is actually returned. Metadata-only results do not advance progress. In automatic-download mode, advance only after qBittorrent returns `already_present`, `submitted`, or `submitted_verified`.
- A latest episode at or below stored progress is `latest_already_handled`: report the latest, current progress, and next target. Do not call qBittorrent for that scheduled latest run, and report `not_attempted`; stored progress is never evidence that a qBittorrent task or downloaded file currently exists.
- Classify tracked-next availability before searching: `not_aired_yet` means the normal scheduled time is still in the future; `availability.state = aired_no_release` means the target has aired but no qualified release was delivered; `airing_schedule_break` means an official same-series gap of 10.5–27.99 days; `long_break_unconfirmed` means a gap of 28 days or more without explicit split-cour evidence; and `split_cour_break` means the current part is finished and an official mainline sequel is explicitly named Part 2/2nd Cour. A completed part without that explicit evidence is `part_finished`. Report dates and evidence, never collapse these cases into “not found.”
- For `not_aired_yet`, schedule breaks, long breaks, and part boundaries, do not search Nyaa or update progress. Only call a long gap split-cour when official structured sequel metadata supports it; title resemblance alone is insufficient.
- Advance an already tracked show only for a verified, strictly newer integer regular episode. Older/same episodes are retrieval-only.
- Never update progress for discovery rows, failed candidates, missing magnets, movies, batches, specials, decimal episodes, or unresolved identity.
- A first qualified result may start tracking only for a confirmed current TV, TV_SHORT, or ONA. Confirmed current works with no qualifying release may become `tracked_waiting`; completed works and non-episodic releases remain stateless.
- Keep metadata-only, movie, batch, rescue, and unresolved calls read-only with `--no-state-update`.

### First-search finalization for an untracked current anime

Finalize an untracked episodic work through `find_anime_release.py`, preserving the discovered season, episode, tier, bounds, subtitle mode, and independently verified search titles. Do not replace this with a low-level `record-found` write. A qualified current work reports `state_update: advanced`; a confirmed current work with no qualified release may report `state_update: tracked_waiting`.

## Failure-only rescue

The seven-day rescue is failure-only. Use it only after ordinary exact-episode discovery or verification fails:

```powershell
python scripts/find_anime_release.py "USER TITLE" --official-air-date --episode 4 --no-state-update --json
```

Proceed only for an eligible currently releasing TV/TV_SHORT/ONA with an exact schedule. Copy the returned scan dates without widening them, preserve every originating constraint, and require `recent_scan.status == complete`. Network, detail, or incomplete-scan failure is not evidence that no release exists.

Run the returned window with `--recent-since DATE --recent-until DATE --current-new-anime`; preserve `--require-zh` when strict Chinese was explicit.

## Final response

Compose from structured evidence. State the exact work/season/episode or movie, release title, size scope, seeders, upward compatibility if used, relevant subtitle evidence, and enqueue result. A recommendation includes its verified magnet in a plain-text code block.

For failure, distinguish not released, identity ambiguity, hard quality/size rejection, strict subtitle rejection, incomplete scan/detail inspection, network failure, and qBittorrent failure. If the latest episode exists but no release qualifies, report that episode and reason rather than returning an older one.
