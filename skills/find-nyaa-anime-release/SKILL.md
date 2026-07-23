---
name: find-nyaa-anime-release
description: Find and verify a Nyaa anime release with read-only local tracking lookup, Agent-led candidate decisions, direct candidate-ID verification, mandatory magnet output for every successful result, and an official post-airing seven-day rescue window for currently releasing new anime. Use for anime titles, nicknames, seasons, latest or specific episodes, tracked next episodes, quality/size floors, stability, Nyaa page links, magnets, complete-season packages, explicit tracking updates, or detail-verified Simplified/Traditional Chinese subtitles. The ordinary path queries Nyaa without metadata services or tracking writes; only a failed current-new-anime search may use AniList's exact episode air date. A 1 GiB default hard floor remains mandatory.
---

# Find Nyaa Anime Release

Use scripts for cheap collection and exact verification. Keep identity, version, season, episode, and fallback decisions with the Agent.

Run commands from this skill directory. Return only releases the user is legally entitled to access.

## Default: probe, use the exact-episode fast path when safe, otherwise discover and verify

### 0. Probe local tracking state

Always run a read-only local-state probe before resolving an ordinary title request:

```powershell
python scripts/airing_watch_state.py probe "USER TITLE"
```

- `not_tracked`: continue with ordinary discovery.
- `tracked`: reuse its season and verified search titles.
- For an explicit continuation request such as “下一集”, “继续追番”, or “找下一集”, target `next_episode`, not the latest release already found.
- An explicit request for “目前已经出的最新一集”, “已发布的最新集”, or equivalent overrides continuation semantics. Discover the latest regular episode that is already available, even when local progress says the next tracked episode is later. Use `latest_known_episode` only as context, not as a forced target.
- For a bare tracked title with no latest/available wording and no explicit episode, treat it as a continuation request and target `next_episode`.
- If that exact next episode has no Nyaa candidate, report that the tracked next episode is not available yet. Never fall back to `latest_known_episode`.

The probe never writes state. Reading existing progress is mandatory; state writes remain opt-in.

### 1. Extract the request

Determine:

- the user's title or established follow-up work;
- exact version/franchise branch and season when stated;
- latest already-available regular episode, tracked next episode, a specific episode, or a whole season; do not collapse “latest already available” into “next tracked episode”;
- explicit size floor/ceiling or quality tier;
- whether Chinese subtitles are required;
- whether the user explicitly prefers a Nyaa page link in addition to the mandatory magnet.

Do not call Bangumi, AniList, or the high-level resolver before an ordinary search. Do not write tracking state.

### 2. Discover directly from Nyaa

Create at most three queries: the user's original title plus no more than two high-confidence aliases. Prefer a complete, broad franchise/work title such as `Mushoku Tensei`; do not spend every query on long season subtitles. Chinese queries are allowed.

Reject visibly damaged aliases. In particular, if metadata or context offers both `ushoku Tensei...` and `Mushoku Tensei...`, discard the truncated form.

For a simple request whose exact regular episode is already known, use the one-command fast path before emitting a 20-row discovery result:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "BROAD ALIAS" --season S01 --episode 3 --fast-verify --min-gib-per-episode 1 --include-magnets --legal-ok --report
```

This path is only for a specific episode or tracked-next episode without strict Chinese subtitles, specials, whole-season validation, real work/version ambiguity, or a request for alternatives. It discovers, applies the compact recommendation, and verifies one ID in the same process. Audit the returned full title, work, season, episode, size, and magnet. If they are correct, stop. If the report says `fast_path_unavailable`, fails verification, or reveals an identity mismatch, fall back to the two-stage discovery below.

Use the normal default cache. RSS/listing cache writes are disposable network caches, not tracking-state writes; do not create an isolated cache or bypass caching merely because progress updates are disabled.

For a latest-episode request, at least one query must be a broad Latin/romaji title. A CJK-only discovery is provisional and must never determine the latest episode:

1. Run the CJK query once.
2. Extract a recurring complete Latin/romaji work title from the returned release titles, excluding group and technical text.
3. Rerun discovery with the original title plus that broad alias.
4. If no reliable alias can be extracted, use the metadata fallback to obtain a search-title hint, then rerun direct discovery.

Run one discovery call:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "BROAD ALIAS" --episode 3 --discover
```

Discovery:

- queries titles in parallel and deduplicates results;
- returns at most 20 recent candidates;
- exposes `nyaa_id`, full title, parsed identity, size, seeders, date, matched queries, and page URL;
- deliberately keeps low-size and subtitle-unverified candidates;
- may expose a compact `fast_path` hint for a simple exact episode, after applying episode/type, hard size, quality, stability, and obvious language-variant checks;
- never returns magnets or fetches detail pages.

Discovery order is recency only, not a recommendation or quality ranking. Never select the first row merely because it is first.
Treat `query_coverage: cjk_only_provisional` as an incomplete search, even when `status` is `found`.
Treat `fast_path` as a script-produced hint, not a final decision: confirm that its full candidate title is the requested work, version, season, and episode before verification.

For a latest-regular request, pass `--intent latest_regular` during discovery. This lets discovery identify a provisional latest regular episode and emit the same compact hint, while the Agent still checks the full candidate set before accepting that episode.

This lets the Agent distinguish “the latest episode exists but fails the user's constraints” from “the episode does not exist.”

### 3. Let the Agent choose candidate IDs

Read full release titles and parsed identities. Group candidates by the exact work/version and season before comparing episode numbers.

- Exclude recaps, previews, OVA/OAD, specials, movies, mini-series, and batches when finding a latest regular episode.
- Do not mix remakes, sequel branches, SAC, films, or older adaptations. For example, treat a 2026 `Ghost in the Shell` series, `Stand Alone Complex`, and the 1995 movie as separate works.
- Treat parsed identity as evidence, not authority. Correct obvious parser mistakes from the full title.
- Identify the newest regular episode first, then evaluate which releases for that episode might satisfy quality/subtitle requirements.
- For a simple specific or tracked-next episode, prefer the one-command `--fast-verify` path above. If it is unavailable, verify exactly one ID from discovery: prefer `fast_path.candidate_id`; otherwise choose the strongest balanced candidate yourself.
- For a simple latest-regular request, discovery must determine the latest episode first; after checking the full title and visible same-episode alternatives, verify exactly one ID.
- If that one verification fails or cannot produce a magnet, try exactly one distinct backup candidate. Stop immediately after the first fully qualified success.
- Build a representative shortlist of up to 3–5 IDs only for strict Chinese subtitles, real work/version ambiguity, conflicting episode identities, special source/group constraints, whole-season validation, or an explicit request for alternatives. Do not expand a simple episode request merely because several redundant encodes exist.
- For a complex shortlist, include the strongest stable/seeded release, the largest reasonable high-quality release, the newest upload, and a title-signaled Chinese release when these are different candidates. Omit redundant encodes that add no distinct advantage.
- Prefer Pareto-superior candidates: at equal work, episode, subtitle eligibility, source, and resolution, a well-seeded reasonably larger release beats a newer but much smaller release.
- Never let seed count or size override the requested work, season, episode, explicit hard bounds, or verified subtitle requirement.

If the candidate set reveals a real version ambiguity that changes the answer, ask the user. Otherwise make the narrowest reasonable inference and continue.

### 4. Verify only selected candidates

Reuse exactly the discovery query set so the short-term RSS cache is hit. On a two-stage simple path, add one `--candidate-id`. For a complex shortlist, add every selected ID with a repeated `--candidate-id`.

Example with explicit Chinese subtitles and a 1 GiB floor:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "BROAD ALIAS" --season S03 --episode 4 --candidate-id 2135067 --min-gib-per-episode 1 --require-zh --include-magnets --legal-ok --report
```

The default hard floor is 1 GiB per regular episode. When the user gives no size bound, pass `--min-gib-per-episode 1`; do not return a smaller release merely because it is the only subtitle-verified candidate. Only use a lower floor when the user explicitly requests or accepts sub-1-GiB releases, and then add `--allow-sub-1g`.

Without an explicit Chinese requirement, omit `--require-zh`. Always add `--include-magnets --legal-ok` to the final candidate-verification call. A successful release search must return a verified magnet even when the user did not explicitly ask for one.

Verification applies season/episode/type and size rules, fetches details only for selected IDs, and returns magnets only after success. A failed report must not be mined for a magnet.

If a selected candidate cannot produce a magnet after successful metadata checks, treat it as incomplete and continue with another shortlisted ID. Never present a release as the final recommendation without a magnet.

Strict Chinese mode requires detail-page evidence for Simplified/Traditional Chinese, CHS/CHT, a Chinese subtitle language track, or a corresponding subtitle file. `MultiSub` alone is not evidence. Title tags alone are not enough.

`--candidate-id` first reuses RSS results. If an ID is absent from those results, the verifier reads `https://nyaa.si/view/ID` directly, requires the detail title to match the user title or an official alias, and reuses that same page for size, seed, hash, file-list, and subtitle checks. This recovers exact resources hidden by Nyaa's spelling-sensitive search.

### 5. Use the official post-airing seven-day rescue only after failure

Do not call AniList or scan Nyaa listing pages after an ordinary success. Trigger this rescue only when the ordinary path has no candidates, or when the exact latest episode exists but no shortlisted release satisfies hard subtitle or size requirements.

Require an exact regular episode. Ask the high-level resolver only for that episode's official AniList air date:

```powershell
python scripts/find_anime_release.py "USER TITLE" --official-air-date --episode 4 --no-state-update --json
```

Proceed only when `status` is `found` and `recent_scan_eligible` is true. The resolver requires a `RELEASING` `TV`, `TV_SHORT`, or `ONA` whose official series start date is no more than 366 days old. This excludes completed new anime and long-running old anime. Treat `not_current_airing`, `not_current_new_anime`, `not_aired_yet`, `schedule_unavailable`, and `ambiguous` as terminal rescue failures. Never infer an air date or current-new-anime status from Nyaa uploads.

Use the returned `scan_since`, `scan_until`, and at most two official aliases exactly as reported:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "OFFICIAL ROMAJI" --alias "OFFICIAL ENGLISH" --episode 1 --discover --recent-since 2026-07-04 --recent-until 2026-07-11 --current-new-anime --require-zh
```

For an episode aired within the last seven days, the window ends today. For an older episode of the same currently releasing new anime, the window is fixed to the official air date through seven days later. This permits an early episode such as episode 1 without opening an unbounded historical search. `--recent-until` may never be more than seven days after `--recent-since`; historical dates also require `--current-new-anime`.

The scan reads Nyaa listing pages covering only that official interval, matches titles locally with Unicode/diacritic and romanization folding, and keeps the same compact discovery candidate schema. It never filters out small or subtitle-unverified candidates.

- Require `recent_scan.status == "complete"` before concluding that no rescue candidate exists.
- Treat `recent_scan.status == "incomplete"` as an incomplete search, even if no candidates were returned.
- Let the Agent select representative IDs from the combined candidates, then run the ordinary targeted verification command.
- Never run a historical interval for a finished anime, an old long-running anime, or a work without an exact official episode schedule.

## Agent decision rules

- For “latest,” discovery determines the latest regular episode. Do not ask metadata services first.
- Never declare a latest episode from a CJK-only discovery. Complete broad Latin/romaji query coverage first, because Chinese fansub results may lag the general release feed by several episodes.
- Apply a 1 GiB hard minimum by default. A subtitle-verified candidate below 1 GiB is still unqualified unless the user explicitly relaxes the floor.
- An explicit `--min-gib-per-episode` or `--max-gib-per-episode` is a hard constraint.
- With no explicit size preference, choose the best balanced release rather than the newest upload. Apply this order: hard user constraints and verified subtitles; correct work/episode; source/resolution; stability/seeders; reasonable size/quality; publication recency.
- On the simple fast path, compare the hinted candidate against the visible exact-episode alternatives once, then verify one ID; do not perform a second broad ranking pass.
- In complex mode, do not describe a release as “best” or return it by default until the representative shortlist has been compared.
- If discovery shows the latest episode but every verified release fails, report that exact reason; do not silently return an older episode.
- If one candidate fails strict subtitle verification, continue through the complex shortlist while the 3–5 candidate budget remains.
- A normal successful search must not call AniList or scan listing pages. The seven-day rescue is failure-only.
- An official date is the sole time-window authority. Do not substitute release timestamps or guessed weekly schedules.
- Copy `scan_since` and `scan_until` from the official report; do not widen or shift the interval.
- Use `--refresh-cache` only when the feed appears stale or a cached strict check needs a fresh RSS snapshot.
- The default cache is shared between discovery, recent listing pages, and verification for five minutes. Override it only with `--cache PATH` when isolation is useful.

## Metadata and legacy fallback

Use `scripts/find_anime_release.py` only when one of these is true:

- the work/version remains ambiguous after discovery;
- episode identities conflict and cannot be resolved from titles;
- every direct query has no candidates and one corrected-query retry also fails;
- a whole-season package needs an authoritative expected episode count;
- the user explicitly requests tracking, continuation from tracked progress, or the next tracked episode;
- the ordinary path failed for an exact episode of a currently releasing new anime and the official post-airing window is needed.

Metadata aliases are hints. Inspect the reported `queries`, correct malformed or over-specific names, and rerun direct discovery when needed.

For metadata-assisted ordinary work, always disable state updates:

```powershell
python scripts/find_anime_release.py "TITLE" --latest --no-state-update --json
```

For a verified complete-season package:

```powershell
python scripts/find_anime_release.py "TITLE" --season S01 --whole-season --min-gib-per-episode 1 --no-state-update --include-magnet --legal-ok --json
```

Only omit `--no-state-update` when the user explicitly says to track, continue tracking, or find the next tracked episode. Read [references/airing-watch-state.md](references/airing-watch-state.md) before changing tracking state. Read [references/quality-ranking.md](references/quality-ranking.md) when a tier/fallback dispute or whole-season quality decision needs more detail.

## Final response

Compose the answer from structured results; do not forward a script's `reply_text` verbatim.

For success, state the exact work/season/episode, title, size, seeders, subtitle evidence when required, and Nyaa page when useful. A magnet is mandatory for every final recommended release; the Nyaa page may be shown alongside it. Put each magnet in its own plain-text code block so it can be copied:

```text
magnet:?xt=urn:btih:...
```

For failure, distinguish among tracked next episode not yet available, no matching episode, latest episode present but below/above the size constraint, Chinese subtitles rejected, official schedule unavailable, work not current/new enough for the rescue, recent scan incomplete, detail checks incomplete, and network/cache failure. Never expose a magnet from an unqualified candidate.
