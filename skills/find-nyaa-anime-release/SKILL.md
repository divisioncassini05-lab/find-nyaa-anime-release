---
name: find-nyaa-anime-release
description: Find and verify Nyaa anime releases with a read-only tracking probe, automatic first-search tracking for confirmed current anime, Agent-led work/season/episode/movie decisions, size-descending search, strict Chinese-subtitle verification, mandatory magnets, whole-season coverage checks, post-airing rescue, and optional qBittorrent enqueue for scheduled runs. Use for titles, nicknames, movies, latest/specific/tracked-next/forced-older episodes, progress, quality or size bounds, Nyaa links, magnets, batches, Chinese subtitles, and automatic scheduled downloads. Discovery is read-only. A qualified regular episode advances watched progress only when strictly newer; confirmed current anime enter tracking on their first search, while forced older/same episodes and a latest episode already watched are retrieval-only and zero-write. Default floors are 1 GiB per regular episode and 10 GiB total per movie.
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

- `not_tracked`: continue with ordinary discovery, then run the first-search finalization below before returning a current episodic anime result.
- `tracked`: reuse its season and verified search titles. When `verified_search_titles` is non-empty, use those titles as the ordinary Nyaa queries first; do not send a broad CJK display title through the ordinary lane because it can match a different work with a similar Chinese name.
- Treat `watched_episode` as the user's actual completed progress. In this user's workflow, a successfully returned qualified regular episode counts as watched because asking the Agent to find it means the user will consume it.
- For an explicit continuation request such as “下一集”, “继续追番”, or “找下一集”, target `next_episode`, not the latest release already found.
- An explicit request for “目前已经出的最新一集”, “已发布的最新集”, or equivalent overrides continuation semantics. Discover the latest regular episode that is already available, even when local progress says the next tracked episode is later. Use `latest_known_episode` only as context, not as a forced target.
- For a bare tracked title with no latest/available wording and no explicit episode, treat it as a continuation request and target `next_episode`.
- An explicit episode request always returns that episode when qualified, even when it is older than `watched_episode`; treat it as retrieval-only and do not change any state field or file timestamp.
- A latest-available request may return an episode equal to or older than `watched_episode`; return it normally but do not change state. Advance only when the returned regular episode is strictly greater than completed progress.
- If that exact next episode has no Nyaa candidate, report that the tracked next episode is not available yet. Never fall back to `latest_known_episode`.

For a tracked work, the local record is the identity decision: use its canonical season, `search_titles`, and especially `verified_search_titles` to target the next episode. The user's Chinese display name may be used only as a separate strict-Chinese supplemental query when Chinese subtitles are required. Do not use a same-number result from an unrelated work matched only by the display-name query.

The probe never writes state. Reading existing progress is mandatory. Discovery and failed direct verification remain read-only. A successful final recommendation for a tracked single regular episode is the user's opt-in signal to commit it as watched. A first request for an untracked work must also enter tracking when metadata confirms that it is a current/still-airing TV, TV_SHORT, or ONA; old/completed shows, movies, OVAs, specials, and unresolved works remain stateless.

### First-search finalization for an untracked current anime

After ordinary discovery identifies the exact work and episode for a `not_tracked` title, do not finalize from the low-level verifier alone. Use the high-level resolver for the final verification and state decision, passing the exact episode and the successful broad search titles:

```powershell
python scripts/find_anime_release.py "USER TITLE" --episode 4 --search-title "BROAD ROMAJI" --search-title "BROAD ENGLISH" --tier browse --include-magnet --legal-ok --json
```

- Omit `--no-state-update`. The resolver must confirm the exact work and whether it is a current/still-airing mainline TV, TV_SHORT, or ONA.
- Preserve explicit size, tier, season, and Chinese-subtitle requirements in this final call.
- On a qualified regular-episode success, require `state_update: advanced`, `tracked: true`, and a verified magnet before reporting that the first search was added. The found episode becomes `watched_episode` and `next_episode` becomes the following integer.
- When a confirmed current anime has no qualified release yet, accept `state_update: tracked_waiting`; preserve the unresolved target without marking it watched.
- If metadata says the work is old/completed, a movie, OVA, special, or otherwise untrackable, return the release normally with `state_update: none` and do not create a record.
- Do not replace this with `airing_watch_state.py update` or `record-found`: those low-level commands cannot prove that an untracked work is a current anime.

### 1. Extract the request

Determine:

- the user's title or established follow-up work;
- whether the request is a movie or episodic work. For a movie, pass `--movie`; use total-file bounds and never reuse the per-episode default;
- exact version/franchise branch and season when stated;
- latest already-available regular episode, tracked next episode, a specific episode, or a whole season; do not collapse “latest already available” into “next tracked episode”;
- explicit size floor/ceiling or quality tier. Map `随便看看` to `--tier browse` (1–2 GiB/episode), `普通画质` to `--tier watch` (2–4 GiB/episode), and `高画质`/`最高画质`/`顶级画质` to `--tier premium` (at least 6 GiB/episode). Pass the named `--tier`; do not silently replace it with the default `--min-gib-per-episode 1`;
- whether Chinese subtitles are required;
- whether the user explicitly prefers a Nyaa page link in addition to the mandatory magnet.

Treat every size phrase as per regular episode unless the request is a movie or the user explicitly says total/package size. For a normal feature film around two hours, default to `--movie --min-total-gib 10`; an explicit user bound overrides that default. For a batch, `size_gib` is the package total, never per-episode evidence. Dividing the total by a claimed episode count yields only a screening average; it cannot prove that every regular episode meets a floor.

Do not call Bangumi, AniList, or the high-level resolver before an ordinary search. Do not write tracking state during discovery or before a candidate is fully qualified.

### 2. Discover directly from Nyaa

Create at most three ordinary-lane queries. For an untracked work, use the user's original title plus no more than two high-confidence aliases. For a tracked work with verified Nyaa titles, use the stored verified titles as the ordinary queries and omit the broad CJK display title from this lane. Prefer a complete, broad franchise/work title such as `Mushoku Tensei`; do not spend every query on long season subtitles. The two Simplified/Traditional supplemental queries below are separate from this ordinary-lane cap.

Reject visibly damaged aliases. In particular, if metadata or context offers both `ushoku Tensei...` and `Mushoku Tensei...`, discard the truncated form.

When Chinese subtitles are a hard requirement and a trustworthy Chinese title is available, add a lightweight Chinese-title lane without removing the ordinary Latin/romaji lane.

```powershell
python scripts/search_nyaa_releases.py "简体标题" --alias "繁體標題" --season S01 --episode 3 --fast-verify --server-sort-size-desc --min-gib-per-episode 1 --max-gib-per-episode 4 --require-zh --trust-cjk-title-for-zh --include-magnets --legal-ok --report
```

- Use the anime name as a short keyword. Try both Simplified and Traditional variants in the same call; do not add long season subtitles or technical terms to these two queries.
- Resolve an exact episode before using this fast command. It asks Nyaa to sort each Simplified/Traditional query with `s=size&o=desc`, reads only a bounded candidate window (at most three pages per query, normally one), and stops once the descending stream reaches an in-range exact candidate. It then keeps only release titles containing the matched Chinese query, applies work/season/episode/type and hard size bounds locally, and selects the largest in-range candidate. It does not fetch a recency-truncated RSS page and pretend that page represents all releases; it also does not crawl every result before sorting.
- `--trust-cjk-title-for-zh` accepts that matched Chinese release title as sufficient subtitle evidence and skips subtitle detail inspection. State this title-based evidence in the final answer.
- Keep the ordinary English/romaji discovery, size filtering, and `--require-zh` detail-page verification path below. Run it as the main lane even when the Chinese lane succeeds; the Chinese lane is a supplement, not a replacement.
- Merge qualified results from both lanes before the final choice. A Latin/romaji-titled candidate still needs ordinary detail-page subtitle evidence; never give it the Chinese-title exemption.
- For a latest request, let the ordinary broad Latin/romaji discovery determine the latest regular episode, then run the Chinese fast lane for that exact episode. Never determine latest from the Chinese lane.
- For a whole-season candidate, first obtain the authoritative episode count through the ordinary path, then run the supplemental lane with that count:

```powershell
python scripts/search_nyaa_releases.py "简体标题" --alias "繁體標題" --season S01 --episodes 12 --whole-season --tier premium --server-sort-size-desc --require-zh --trust-cjk-title-for-zh --include-magnets --legal-ok --report
```

  The detail-page file list remains mandatory for episode coverage and per-file size checks. The Chinese-title exemption skips only redundant subtitle inspection.
- If no trustworthy Chinese title is already available, use only the ordinary lane; do not call metadata merely to manufacture one.

For a simple request whose exact regular episode is already known, use the one-command fast path before emitting a 20-row discovery result:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "BROAD ALIAS" --season S01 --episode 3 --fast-verify --server-sort-size-desc --min-gib-per-episode 1 --include-magnets --legal-ok --report
```

This path is only for a specific episode or tracked-next episode without detail-verified strict Chinese subtitles, specials, whole-season validation, real work/version ambiguity, or a request for alternatives. The explicit `--trust-cjk-title-for-zh` supplemental lane above is the only strict-Chinese exception. It discovers, applies the compact recommendation, and verifies one ID in the same process. Audit the returned full title, work, season, episode, size, and magnet. If they are correct, keep it for comparison with the ordinary lane. If the report says `fast_path_unavailable`, fails verification, or reveals an identity mismatch, continue with the ordinary path.

Use the normal default cache. RSS/listing cache writes are disposable network caches, not tracking-state writes; do not create an isolated cache or bypass caching merely because progress updates are disabled.

For a latest-episode request, at least one query must be a broad Latin/romaji title. A CJK-only discovery is provisional and must never determine the latest episode:

1. Run the CJK query once.
2. Extract a recurring complete Latin/romaji work title from the returned release titles, excluding group and technical text.
3. Rerun discovery with the original title plus that broad alias.
4. If no reliable alias can be extracted, use the metadata fallback to obtain a search-title hint, then rerun direct discovery.

Run the ordinary mainstream discovery call. For a known exact episode, whole-season package, premium tier, or explicit size bounds, add `--server-sort-size-desc`; the script also enables this mode automatically for those cases:

```powershell
python scripts/search_nyaa_releases.py "USER TITLE" --alias "BROAD ALIAS" --episode 3 --discover --server-sort-size-desc
```

For a movie, use a total-size search. Do not pass episode or season arguments:

```powershell
python scripts/search_nyaa_releases.py "MOVIE TITLE" --alias "BROAD ALIAS" --movie --discover --server-sort-size-desc --min-total-gib 10 --require-zh --legal-ok --report
```

Discovery:

- queries titles in parallel and deduplicates results;
- returns at most 20 compact candidates;
- exposes `nyaa_id`, full title, parsed identity, size, `size_scope`, `per_episode_size_gib`, whether whole-season verification is required, seeders, date, matched queries, and page URL;
- deliberately keeps low-size and subtitle-unverified candidates;
- may expose a compact `fast_path` hint for a simple exact episode, after applying episode/type, hard size, quality, stability, and obvious language-variant checks;
- never returns magnets or fetches detail pages.

For an exact episode, discovery performs one bounded title-recovery retry when CJK-matched same-work candidates expose a slash-delimited Latin/romaji title but none of the configured Latin queries actually matched. It reports `alias_recovery`, adds the recovered title to `queries`, and merges the retry results. Reuse that expanded query set during verification.

For unconstrained/latest discovery, `candidate_source: nyaa_rss_recent` and `ordering: published_desc_only_not_quality_rank` mean the displayed order is recency only. For size-driven discovery, require `candidate_source: nyaa_html_size_desc` and `ordering: nyaa_server_size_desc_then_local_size_desc_not_quality_rank`; Nyaa performs the initial `s=size&o=desc` ordering, the script preserves size-descending display order across merged queries, and local work/episode/size rules apply to that bounded window. Never select the first row merely because it is first. Check the work, episode, bounds, and verification state.
For `size_scope: movie_total`, compare `size_gib` only with movie total bounds; never describe it as per-episode size. For `size_scope: batch_total`, never compare `size_gib` with a per-episode floor and never describe the package as size-qualified. Require `per_episode_size_gib` for a single-episode comparison. A batch with `requires_whole_season_verification: true` must switch to the verified whole-season path below before recommendation.
Treat `query_coverage: cjk_only_provisional` as incomplete when determining the latest episode or concluding that no qualified release exists, even when `status` is `found`. A supplied Latin alias is not proof that it worked: inspect `latin_query_match`. If it is false and a same-work CJK candidate exposes a complete Latin/romaji title, require the corrected retry or the reported automatic `alias_recovery` before concluding that no qualified release exists. The supplemental Chinese lane never replaces ordinary mainstream query coverage.
Treat `fast_path` as a script-produced hint, not a final decision: confirm that its full candidate title is the requested work, version, season, and episode before verification.

For a latest-regular request, pass `--intent latest_regular` during discovery. This lets discovery identify a provisional latest regular episode and emit the same compact hint, while the Agent still checks the full candidate set before accepting that episode.

This lets the Agent distinguish “the latest episode exists but fails the user's constraints” from “the episode does not exist.”

### 3. Let the Agent choose candidate IDs

Read full release titles and parsed identities. Group candidates by the exact work/version and season before comparing episode numbers.

- Exclude recaps, previews, OVA/OAD, specials, movies, mini-series, and batches when finding a latest regular episode.
- For an explicit movie request, use `--movie` and select movie/unknown-episode identities under the movie total-size policy; do not force the title into a regular-episode intent.
- Do not mix remakes, sequel branches, SAC, films, or older adaptations. For example, treat a 2026 `Ghost in the Shell` series, `Stand Alone Complex`, and the 1995 movie as separate works.
- Treat parsed identity as evidence, not authority. Correct obvious parser mistakes from the full title.
- Treat a candidate found only through a tracked work's broad CJK display title as provisional. If its full title belongs to another canonical work, reject it before verification and do not expose it as an alternative or failure candidate.
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

For a movie, verify the selected ID with a total-size floor:

```powershell
python scripts/search_nyaa_releases.py "MOVIE TITLE" --alias "BROAD ALIAS" --movie --candidate-id 2135067 --min-total-gib 10 --require-zh --include-magnets --legal-ok --report
```

The default hard floor is 1 GiB per regular episode. When the user gives no episode size bound, pass `--min-gib-per-episode 1`; do not return a smaller release merely because it is the only subtitle-verified candidate. Only use a lower floor when the user explicitly requests or accepts sub-1-GiB releases, and then add `--allow-sub-1g`. Movies use a separate default hard floor of 10 GiB total; pass `--movie --min-total-gib 10`, and relax it only when the user explicitly accepts a smaller movie release.

Without an explicit Chinese requirement, omit `--require-zh`. Always add `--include-magnets --legal-ok` to the final candidate-verification call. A successful release search must return a verified magnet even when the user did not explicitly ask for one.

Verification applies season/episode/type and size rules, fetches details only for selected IDs, and returns magnets only after success. A failed report must not be mined for a magnet.

If a selected candidate cannot produce a magnet after successful metadata checks, treat it as incomplete and continue with another shortlisted ID. Never present a release as the final recommendation without a magnet.

### 4.1 Enqueue the final magnet for scheduled runs

For a Codex cron/automation run, or when the user explicitly requests automatic downloading, submit exactly the final fully qualified magnet to qBittorrent. Do not enqueue discovery rows, backups that failed verification, or magnets exposed by failed reports. Ordinary interactive searches remain retrieval-only unless the user asks to download.

For the ordinary verifier path, enqueue after final qualification and before `record-found`:

```powershell
python scripts/qbittorrent_submit.py "MAGNET" --save-path "C:\User_data\Download\qBittorrent" --json
```

- Accept `already_present`, `submitted`, or `submitted_verified` with `ok: true` as success.
- On submission failure, return the qualified magnet with the qBittorrent error, but do not advance watched progress. Let the next scheduled run retry the same episode.
- The helper discovers the local qBittorrent executable, uses its native `--skip-dialog=true` and `--add-stopped=false` URL handoff, and suppresses the add-torrent dialog. Do not enable WebUI or store a WebUI password.
- Keep automation prompts minimal. `$find-nyaa-anime-release TITLE` is sufficient; do not repeat these rules in the task prompt.

When the high-level resolver performs final verification or first-search tracking, pass the enqueue option so qBittorrent handoff happens before any progress write:

```powershell
python scripts/find_anime_release.py "USER TITLE" --episode 4 --tier browse --include-magnet --legal-ok --enqueue-qbittorrent --json
```

After the final candidate is fully qualified and its magnet will be returned, commit a tracked single regular episode as watched:

```powershell
python scripts/airing_watch_state.py record-found "USER TITLE" --episode 4
```

- Run this exactly once after success for an already tracked, current/still-airing single regular episode only when the returned episode is strictly greater than completed progress from the probe.
- Accept `recorded` as an advance and report the updated `watched_episode` and `next_episode` when relevant. Accept `unchanged` as a successful retrieval-only result and do not claim that state changed.
- Do not call it for discovery rows, failed or unqualified candidates, missing magnets, specials, decimal episodes, movies, whole-season packages, or untracked titles. Route untracked episodic works through the first-search high-level finalization instead.
- The command is monotonic and zero-write for an equal or older episode: it returns `unchanged` without rewriting the state file, notes, or timestamp.

In the ordinary mainstream lane, strict Chinese mode requires detail-page evidence for Simplified/Traditional Chinese, CHS/CHT, a Chinese subtitle language track, or a corresponding subtitle file. `MultiSub` alone is not evidence, and a Latin/romaji title tag is not enough. Only the separate Simplified/Traditional query lane may use `--trust-cjk-title-for-zh`; there, an exact matched Chinese release title is accepted without subtitle detail inspection.

`--candidate-id` first reuses RSS results. If an ID is absent from those results, the verifier reads `https://nyaa.si/view/ID` directly, requires the detail title to match the user title or an official alias, and reuses that same page for size, seed, hash, file-list, and subtitle checks. This recovers exact resources hidden by Nyaa's spelling-sensitive search.

For any batch or complete-season recommendation—even when a bare title led the Agent to prefer a batch—do not use ordinary candidate-ID verification as the final check. Obtain an authoritative expected regular-episode count, then run the high-level `--whole-season` command. It must inspect the Nyaa file list, exclude extras, verify complete coverage, and enforce named tiers or explicit min/max bounds on the regular files. Total package size can reject an impossible package (`total < episode_count × floor`) but can never qualify one.

A request for one season does not require an exact-single-season package. Keep a multi-season collection such as `S1+S2` eligible when it contains the requested season, the detail file list identifies seasons unambiguously, the requested season has complete regular-episode coverage, and the collection's mapped regular files satisfy the requested tier or explicit per-file bounds. Prefer a qualified exact-season package when one exists; otherwise a qualified multi-season collection may be the final recommendation. Label it as a multi-season collection and report the full package total separately.

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
- Never use Nyaa size order to infer the latest episode. Determine latest from the ordinary recency lane first; after the exact episode is known, use the native size-descending window to find the best release for that episode.
- Never declare a latest episode from a CJK-only discovery. Complete broad Latin/romaji query coverage first, because Chinese fansub results may lag the general release feed by several episodes.
- For strict Chinese subtitles, preserve the ordinary Latin/romaji discovery, size filter, and detail verification. Add the Simplified-plus-Traditional title lane as a quick supplement; trust only exact matched Chinese release titles, require its Nyaa-native size-descending source, order its exact-episode candidates by size descending, and never use it to determine latest.
- For a known episode, whole season, premium tier, or explicit size range, prefer Nyaa's server-side `s=size&o=desc` search. Local sorting is only the final merge/display step over the bounded pages returned by Nyaa, not a substitute for server-side coverage.
- When the user requests one season, do not discard a package merely because it also contains other seasons. Verify the requested season's complete coverage and the quality of all mapped regular files in the collection; prefer an exact-season package but allow a qualified superset package.
- Apply a 1 GiB hard minimum by default. A subtitle-verified candidate below 1 GiB is still unqualified unless the user explicitly relaxes the floor.
- Honor named quality tiers before discovery. In particular, `高画质` is `premium`, not the default browse policy; pass `--tier premium`. For a batch, every regular episode file must meet the 6 GiB floor unless a qualifying BDMV/remux source rule applies.
- An explicit `--min-gib-per-episode` or `--max-gib-per-episode` is a hard constraint.
- Never compare a batch total with a per-episode bound. If `per_episode_size_gib` is null or whole-season verification is required, the candidate is not yet qualified.
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
- every direct query has no candidates and one corrected-query retry also fails, or exact-episode CJK candidates exist but the bounded Latin-alias recovery is unavailable or fails to produce a qualified candidate;
- a whole-season package needs an authoritative expected episode count;
- the user explicitly requests tracking, continuation from tracked progress, or the next tracked episode;
- the ordinary path failed for an exact episode of a currently releasing new anime and the official post-airing window is needed.

Metadata aliases are hints. Inspect the reported `queries`, correct malformed or over-specific names, and rerun direct discovery when needed.

For metadata-assisted ordinary work that is not the first-search finalization of an untracked episodic anime, disable state updates:

```powershell
python scripts/find_anime_release.py "TITLE" --latest --no-state-update --json
```

For a verified complete-season package:

```powershell
python scripts/find_anime_release.py "TITLE" --season S01 --whole-season --tier premium --no-state-update --include-magnet --legal-ok --json
```

For a scheduled or explicitly automatic run, add `--enqueue-qbittorrent` to either high-level command. Keep `--no-state-update` rules unchanged.

Use the tier requested by the user; the example shows `高画质`. For an explicit per-episode floor, replace the tier with `--min-gib-per-episode N`. Never recommend a discovery batch before this command returns verified `coverage` with `quality_fit: true`.

For a tracked current anime, omit `--no-state-update` when the high-level resolver itself will return the fully qualified single regular episode; that success must record the episode as watched. Also omit it for first-search finalization of an untracked episodic work so confirmed current anime are created automatically. Keep `--no-state-update` for metadata-only inspection, read-only discovery, official-date recovery, movies, specials, batches, and any result whose identity or current-airing eligibility is unresolved. Read [references/airing-watch-state.md](references/airing-watch-state.md) before changing tracking state. Read [references/quality-ranking.md](references/quality-ranking.md) when a tier/fallback dispute or whole-season quality decision needs more detail.

## Final response

Compose the answer from structured results; do not forward a script's `reply_text` verbatim.

For success, state the exact work/season/episode or movie identity, title, size, seeders, subtitle evidence when required, and Nyaa page when useful. For an automatic run, also state whether qBittorrent accepted the magnet or already had it. Distinguish `matched Chinese release title` evidence from `detail-page verified Chinese subtitles`; do not claim a detail check occurred on the supplemental title-trust lane. For a movie, label the value as total size. For a batch, label the package total separately and state the verified regular-file average/min/max from `coverage`; never relabel the package total as per-episode size. A magnet is mandatory for every final recommended release; the Nyaa page may be shown alongside it. Put each magnet in its own plain-text code block so it can be copied:

```text
magnet:?xt=urn:btih:...
```

For failure, distinguish among tracked next episode not yet available, no matching episode, latest episode present but below/above the size constraint, Chinese subtitles rejected, official schedule unavailable, work not current/new enough for the rescue, recent scan incomplete, detail checks incomplete, and network/cache failure. Never expose a magnet from an unqualified candidate.
