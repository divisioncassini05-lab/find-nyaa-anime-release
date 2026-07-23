---
name: find-nyaa-anime-release
description: Find and verify a Nyaa anime release with read-only local tracking lookup and a two-stage script-collection and Agent-decision workflow. Use for anime titles, nicknames, seasons, latest or specific episodes, tracked next episodes, quality/size floors, stability, Nyaa page links, magnets, complete-season packages, explicit tracking updates, or detail-verified Simplified/Traditional Chinese subtitles. The default path reads existing tracking progress without writing it, queries Nyaa directly without metadata services, exposes compact candidates for Agent judgment, then verifies only selected Nyaa IDs with a 1 GiB default hard floor.
---

# Find Nyaa Anime Release

Use scripts for cheap collection and exact verification. Keep identity, version, season, episode, and fallback decisions with the Agent.

Run commands from this skill directory. Return only releases the user is legally entitled to access.

## Default: probe, discover, decide, verify

### 0. Probe local tracking state

Always run a read-only local-state probe before resolving an ordinary title request:

```powershell
python scripts/airing_watch_state.py probe "USER TITLE"
```

- `not_tracked`: continue with ordinary discovery.
- `tracked`: reuse its season and verified search titles.
- For a tracked title-only request with no explicit episode, target `next_episode`, not the latest release already found.
- If that exact next episode has no Nyaa candidate, report that the tracked next episode is not available yet. Never fall back to `latest_known_episode`.

The probe never writes state. Reading existing progress is mandatory; state writes remain opt-in.

### 1. Extract the request

Determine:

- the user's title or established follow-up work;
- exact version/franchise branch and season when stated;
- latest regular episode, a specific episode, or a whole season;
- explicit size floor/ceiling or quality tier;
- whether Chinese subtitles are required;
- whether a page link or magnet was requested.

Do not call Bangumi, AniList, or the high-level resolver before an ordinary search. Do not write tracking state.

### 2. Discover directly from Nyaa

Create at most three queries: the user's original title plus no more than two high-confidence aliases. Prefer a complete, broad franchise/work title such as `Mushoku Tensei`; do not spend every query on long season subtitles. Chinese queries are allowed.

Reject visibly damaged aliases. In particular, if metadata or context offers both `ushoku Tensei...` and `Mushoku Tensei...`, discard the truncated form.

For a latest-episode request, at least one query must be a broad Latin/romaji title. A CJK-only discovery is provisional and must never determine the latest episode:

1. Run the CJK query once.
2. Extract a recurring complete Latin/romaji work title from the returned release titles, excluding group and technical text.
3. Rerun discovery with the original title plus that broad alias.
4. If no reliable alias can be extracted, use the metadata fallback to obtain a search-title hint, then rerun direct discovery.

Run one discovery call:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "BROAD ALIAS" --discover
```

Discovery:

- queries titles in parallel and deduplicates results;
- returns at most 20 recent candidates;
- exposes `nyaa_id`, full title, parsed identity, size, seeders, date, matched queries, and page URL;
- deliberately keeps low-size and subtitle-unverified candidates;
- never returns magnets or fetches detail pages.

Discovery order is recency only, not a recommendation or quality ranking. Never select the first row merely because it is first.
Treat `query_coverage: cjk_only_provisional` as an incomplete search, even when `status` is `found`.

This lets the Agent distinguish “the latest episode exists but fails the user's constraints” from “the episode does not exist.”

### 3. Let the Agent choose candidate IDs

Read full release titles and parsed identities. Group candidates by the exact work/version and season before comparing episode numbers.

- Exclude recaps, previews, OVA/OAD, specials, movies, mini-series, and batches when finding a latest regular episode.
- Do not mix remakes, sequel branches, SAC, films, or older adaptations. For example, treat a 2026 `Ghost in the Shell` series, `Stand Alone Complex`, and the 1995 movie as separate works.
- Treat parsed identity as evidence, not authority. Correct obvious parser mistakes from the full title.
- Identify the newest regular episode first, then evaluate which releases for that episode might satisfy quality/subtitle requirements.
- Build a representative shortlist for that exact episode. If at least three plausible releases exist, verify 3–5 IDs; if two exist, verify both. Verify only one ID only when it is the sole plausible release.
- Include the strongest stable/seeded release, the largest reasonable high-quality release, the newest upload, and a title-signaled Chinese release when these are different candidates. Omit redundant encodes that add no distinct advantage.
- Prefer Pareto-superior candidates: at equal work, episode, subtitle eligibility, source, and resolution, a well-seeded reasonably larger release beats a newer but much smaller release.
- Never let seed count or size override the requested work, season, episode, explicit hard bounds, or verified subtitle requirement.

If the candidate set reveals a real version ambiguity that changes the answer, ask the user. Otherwise make the narrowest reasonable inference and continue.

### 4. Verify only selected candidates

Reuse exactly the discovery query set so the short-term RSS cache is hit. Add every shortlisted ID with a repeated `--candidate-id`.

Example with explicit Chinese subtitles and a 1 GiB floor:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "BROAD ALIAS" --season S03 --episode 4 --candidate-id 2135067 --min-gib-per-episode 1 --require-zh --include-magnets --legal-ok --report
```

The default hard floor is 1 GiB per regular episode. When the user gives no size bound, pass `--min-gib-per-episode 1`; do not return a smaller release merely because it is the only subtitle-verified candidate. Only use a lower floor when the user explicitly requests or accepts sub-1-GiB releases, and then add `--allow-sub-1g`.

Without an explicit Chinese requirement, omit `--require-zh`. Add `--include-magnets --legal-ok` only when a magnet is requested.

Verification applies season/episode/type and size rules, fetches details only for selected IDs, and returns magnets only after success. A failed report must not be mined for a magnet.

Strict Chinese mode requires detail-page evidence for Simplified/Traditional Chinese, CHS/CHT, a Chinese subtitle language track, or a corresponding subtitle file. `MultiSub` alone is not evidence. Title tags alone are not enough.

## Agent decision rules

- For “latest,” discovery determines the latest regular episode. Do not ask metadata services first.
- Never declare a latest episode from a CJK-only discovery. Complete broad Latin/romaji query coverage first, because Chinese fansub results may lag the general release feed by several episodes.
- Apply a 1 GiB hard minimum by default. A subtitle-verified candidate below 1 GiB is still unqualified unless the user explicitly relaxes the floor.
- An explicit `--min-gib-per-episode` or `--max-gib-per-episode` is a hard constraint.
- With no explicit size preference, choose the best balanced release rather than the newest upload. Apply this order: hard user constraints and verified subtitles; correct work/episode; source/resolution; stability/seeders; reasonable size/quality; publication recency.
- Do not describe a release as “best” or return it by default until the representative shortlist has been compared.
- If discovery shows the latest episode but every verified release fails, report that exact reason; do not silently return an older episode.
- If one candidate fails subtitle verification, continue through the shortlisted IDs while the 3–5 candidate budget remains.
- Use `--refresh-cache` only when the feed appears stale or a cached strict check needs a fresh RSS snapshot.
- The default cache is shared between discovery and verification for five minutes. Override it only with `--cache PATH` when isolation is useful.

## Metadata and legacy fallback

Use `scripts/find_anime_release.py` only when one of these is true:

- the work/version remains ambiguous after discovery;
- episode identities conflict and cannot be resolved from titles;
- every direct query has no candidates and one corrected-query retry also fails;
- a whole-season package needs an authoritative expected episode count;
- the user explicitly requests tracking, continuation from tracked progress, or the next tracked episode.

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

For success, state the exact work/season/episode, title, size, seeders, subtitle evidence when required, and Nyaa page when useful. Put each magnet in its own plain-text code block so it can be copied:

```text
magnet:?xt=urn:btih:...
```

For failure, distinguish among tracked next episode not yet available, no matching episode, latest episode present but below/above the size constraint, Chinese subtitles rejected, detail checks incomplete, and network/cache failure. Never expose a magnet from an unqualified candidate.
