---
name: find-nyaa-anime-release
description: Find and verify Nyaa anime releases with Agent-reviewed work, season, episode, and movie identity; default soft preference for Chinese subtitles; strict Chinese verification only when explicitly required; hard quality and size checks; mandatory magnets; optional qBittorrent enqueue; and monotonic tracking for current anime. Use for latest, specific, tracked-next, movie, whole-season, quality, size, subtitle, magnet, progress, and scheduled-download requests. Discovery is read-only. Default floors are 1 GiB per regular episode and 10 GiB total per movie.
---

# Find Nyaa Anime Release

Use the scripts for deterministic collection, parsing evidence, detail and magnet verification, qBittorrent submission, and monotonic state writes. The Agent must read full release titles and decide the actual work/version, season, regular episode versus special, latest episode, movie/batch identity, and final candidate.

Run commands from this skill directory. Return only releases the user is legally entitled to access.

## Workflow

Follow one compact path: parse request and state → discover candidates → Agent judgment → exact verification → optional enqueue and progress update → failure-only rescue.

### 1. Parse the request and state

Always run a read-only local-state probe before an ordinary title search:

```powershell
python scripts/airing_watch_state.py probe "USER TITLE"
```

- For a tracked title, use its canonical season and verified search titles; when `verified_search_titles` is non-empty, use those titles as the ordinary Nyaa queries first. The record establishes work identity, not the target episode.
- Explicit episode, continuation/“下一集”, and latest wording win. A bare tracked title means `next_episode` interactively, but “latest already available” means the latest regular episode in a Codex automation run.
- Scheduled latest discovery must complete successfully; never fall back to stale `next_episode` after incomplete query coverage, network failure, or unresolved identity.
- An explicit older/same episode and a latest result not newer than `watched_episode` are retrieval-only and must not rewrite state.
- Determine movie versus episodic work, branch/version, season, target episode or whole season, named quality tier, explicit size bounds, and any source/group requirement. Script parsing and `fast_path` are evidence, not authority.
- Map `随便看看` to `--tier browse`, `普通画质` to `--tier watch`, and `高画质`/`最高画质`/`顶级画质` to `--tier premium`. The default hard floor is 1 GiB per regular episode. A normal movie defaults to `--movie --min-total-gib 10`. Explicit user bounds are hard.
- `--allow-upward-compatibility` is used only when the caller enables it. Prefer the named tier; if none qualifies, a higher-tier result may be selected, but the tier floor and every explicit maximum remain hard. Label the result as upward compatible.

Read [references/airing-watch-state.md](references/airing-watch-state.md) before any tracking write or difficult latest/next decision. Read [references/quality-ranking.md](references/quality-ranking.md) for tier fallback, upward compatibility, batch math, or unusual ranking disputes.

#### Subtitle mode: exactly two defaults

- If the originating user or automation prompt explicitly requires Simplified Chinese, Traditional Chinese, or Chinese subtitles, use strict mode and pass `--require-zh`. Chinese subtitle evidence is then a hard qualification condition.
- Else, pass `--want-zh`. This is only a soft ranking preference; never reject an otherwise qualified release because Chinese subtitles are absent or unverified.

A Chinese title, alias, result, UI language, tracking record, automation memory, prior Agent summary, or retry reason does not create a hard subtitle requirement. Every retry must reread the originating prompt and inherit only its constraints, not conditions invented by an earlier run. Do not add an “exclude Chinese subtitles” mode; if the user later asks for a genuinely different third case, handle that request separately.

### 2. Discover candidates

Use at most three broad, high-confidence ordinary queries. For tracked works prefer stored verified Latin/romaji titles; do not let a broad CJK display-name match replace work-identity review. Discovery is read-only, returns no magnet, and deliberately retains candidates that still need exact checks. RSS/listing cache writes are disposable network caches, not tracking-state writes.

For a known regular episode, use the compact path:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "BROAD ALIAS" --season S01 --episode 3 --fast-verify --server-sort-size-desc --min-gib-per-episode 1 --want-zh --include-magnets --legal-ok --report
```

For latest discovery, first use the ordinary Latin/romaji recency lane with `--intent latest_regular`; only after the Agent confirms the exact episode should size-driven exact-episode comparison run. Never declare a latest episode from a CJK-only discovery. If CJK-only results expose a complete Latin/romaji alias, rerun the broad lane; if they do not, use metadata only to recover a search-title hint.

For an ordinary movie:

```powershell
python scripts/search_nyaa_releases.py "MOVIE TITLE" --alias "BROAD ALIAS" --movie --discover --server-sort-size-desc --min-total-gib 10 --want-zh --legal-ok --report
```

For strict Chinese only, a trustworthy Chinese title may add this supplemental exact-episode lane:

```powershell
python scripts/search_nyaa_releases.py "简体标题" --alias "繁體標題" --season S01 --episode 3 --fast-verify --server-sort-size-desc --min-gib-per-episode 1 --require-zh --trust-cjk-title-for-zh --include-magnets --legal-ok --report
```

Try both Simplified and Traditional variants in the same call. `--trust-cjk-title-for-zh` accepts an exact matched Chinese release title and skips subtitle detail inspection; report that title-based evidence accurately. Keep the ordinary broad lane and its strict detail-verification path: the Chinese lane is a supplement, not a replacement. For latest, let the ordinary broad Latin/romaji discovery determine the latest regular episode before querying the strict Chinese lane for that exact episode.

### 3. Agent judgment

Read every relevant full title. Group by exact work/version and season, correct parser mistakes, and exclude recaps, previews, OVA/OAD, specials, movies, mini-series, and batches from latest regular-episode decisions. Never select the first row merely because it is first.

For a simple exact or latest regular episode, compare visible same-episode alternatives once and verify exactly one ID. Prefer the `fast_path` hint only after auditing identity, season, episode, type, size, and visible alternatives. If verification or magnet extraction fails, try exactly one distinct backup candidate.

Build a representative shortlist of up to 3–5 IDs only for strict Chinese subtitles, real identity ambiguity, conflicting episode parsing, whole-season validation, special source/group constraints, or an explicit request for alternatives.

Apply hard identity, type, quality tier, size, source, and explicit subtitle constraints before ranking. In default `--want-zh` mode:

- Compare the same work, season, episode, quality class, and hard size eligibility first.
- Use the existing swarm score; add no fixed seed threshold.
- When swarm health is comparable, prefer the Chinese-subtitled candidate.
- A dead or clearly weaker Chinese candidate loses to a healthy non-Chinese candidate.
- Chinese signals never cross a quality tier, break a hard size bound, trigger upward compatibility, or justify a quality downgrade.
- Do not fetch a detail page solely to resolve this soft preference. Use discovery/title evidence already available; exact verification may still fetch details for its ordinary non-subtitle checks.

If a real work/version ambiguity would change the answer, ask the user. Otherwise make the narrowest supported inference and continue.

### 4. Verify the selected release

Reuse the discovery query set and verify only selected IDs. Ordinary mode includes `--want-zh`:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "BROAD ALIAS" --season S01 --episode 3 --candidate-id 2135067 --min-gib-per-episode 1 --want-zh --include-magnets --legal-ok --report
```

Explicit hard Chinese mode replaces `--want-zh` with `--require-zh`:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "BROAD ALIAS" --season S01 --episode 3 --candidate-id 2135067 --min-gib-per-episode 1 --require-zh --include-magnets --legal-ok --report
```

Strict ordinary-lane verification requires actual Simplified/Traditional Chinese, CHS/CHT, a Chinese subtitle track, or a corresponding subtitle file. `MultiSub` alone is insufficient. Without explicit hard Chinese wording, subtitle absence or uncertainty must not produce `subtitle_unqualified`.

Always require `--include-magnets --legal-ok` on final verification. Never expose a magnet from a failed or unqualified report. If an ID is missing from cached discovery, the verifier reads `https://nyaa.si/view/ID` directly and rechecks title/alias, size, seed, hash, files, and any hard subtitle condition.

Movie verification uses `--movie --candidate-id ID --min-total-gib 10 --want-zh`; never apply per-episode bounds to a movie. For a whole season, use the high-level verifier with an authoritative expected episode count:

```powershell
python scripts/find_anime_release.py "TITLE" --season S01 --whole-season --tier premium --want-zh --no-state-update --include-magnet --legal-ok --json
```

It must inspect the file list, exclude extras, verify complete regular-episode coverage, and enforce per-file quality. Package total alone never proves per-episode qualification. A qualified multi-season collection may satisfy one requested season when that season is mapped unambiguously; prefer an exact-season package.

#### First-search finalization for an untracked current anime

After read-only discovery of an untracked episodic work, finalise the exact result through the high-level resolver rather than low-level `record-found`:

```powershell
python scripts/find_anime_release.py "USER TITLE" --episode 4 --search-title "BROAD ROMAJI" --search-title "BROAD ENGLISH" --tier browse --want-zh --include-magnet --legal-ok --json
```

Preserve the actual tier, bounds, season, and subtitle mode. Omit `--no-state-update`. A qualified current/still-airing TV, TV_SHORT, or ONA success must report `state_update: advanced`, `tracked: true`, and a verified magnet. If the current work is confirmed but no release qualifies yet, accept `state_update: tracked_waiting` without marking the episode watched. Movies, OVAs, specials, completed/old shows, and unresolved works remain stateless.

### 5. Enqueue and update progress

For a scheduled run or explicit download request, enqueue exactly the final qualified release, after a final audit that a scheduled bare-title candidate equals the latest episode established by this run:

```powershell
python scripts/qbittorrent_submit.py "MAGNET" --source-url "NYAA_PAGE_URL" --save-path "C:\User_data\Download\qBittorrent" --json
```

Accept only `ok: true` with `already_present`, `submitted`, or `submitted_verified`. Require the source URL when available so torrent metadata and infohash are validated. On submission failure, report the qualified magnet and error but do not advance progress.

For an already tracked current anime, after a qualified magnet is returned—or qBittorrent accepts/already has it in an automatic run—advance only a strictly newer integer regular episode:

```powershell
python scripts/airing_watch_state.py record-found "USER TITLE" --episode 4
```

`record-found` is monotonic. `recorded` advances `watched_episode` and `next_episode`; `unchanged` is retrieval-only and must not rewrite state. Never update for discovery rows, failed/unqualified candidates, missing magnets, movies, batches, specials, decimal episodes, or unresolved identity. Untracked works use first-search finalization above.

When the high-level resolver handles final verification, pass `--enqueue-qbittorrent` so submission occurs before its state write. Keep metadata-only, movie, batch, rescue, and unresolved calls read-only with `--no-state-update`.

### 6. Failure-only rescue

The seven-day rescue is failure-only. Use it only after ordinary discovery/verification fails for an exact regular episode; never run it after success. Obtain the official date first:

```powershell
python scripts/find_anime_release.py "USER TITLE" --official-air-date --episode 4 --no-state-update --json
```

Proceed only for an eligible currently releasing TV/TV_SHORT/ONA with an exact schedule. Copy the returned dates without guessing or widening them:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "OFFICIAL ROMAJI" --episode 4 --discover --recent-since 2026-07-04 --recent-until 2026-07-11 --current-new-anime --want-zh
```

In explicit hard Chinese mode, replace `--want-zh` with `--require-zh`. Require `recent_scan.status == complete`; an incomplete scan or network/detail failure is not proof that no release exists. Let the Agent choose and verify from the combined candidates using the same rules.

Retries inherit the originating prompt's identity, quality, size, subtitle mode, enqueue, and progress rules. They must not promote a previous failure explanation into a new constraint.

## Final response

Compose from structured evidence, not a script's prose. State the exact work/season/episode or movie, title, size scope, seeders, upward compatibility when used, subtitle evidence when relevant, and automatic submission result. A final recommendation always includes a verified magnet; put it in its own plain-text code block. Never expose an unqualified magnet.

For failure, distinguish not released, identity ambiguity, hard quality/size failure, strict subtitle rejection, incomplete detail/recent scan, network failure, and qBittorrent failure. If latest exists but no release qualifies, report that exact episode and reason; never silently return an older episode.
