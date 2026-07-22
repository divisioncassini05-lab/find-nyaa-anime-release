---
name: find-nyaa-anime-release
description: Find one qualified Nyaa anime release from an anime title, nickname, season, episode, quality tier, size floor, stability requirement, subtitle preference, website-link request, or a follow-up to an established anime. Resolve new-airing aliases, distinguish regular episodes from specials, maintain only current-airing progress, and require detail-verified Simplified or Traditional Chinese subtitles only when the user explicitly asks for a Chinese-subtitled release.
---

# Find Nyaa Anime Release

Run `scripts/find_anime_release.py` before browser or manual Nyaa work. Treat its structured report as the source of truth; do not infer why a result disappeared from a title regex. The only normal second invocation is the bounded `needs_web_resolution` loop described below.

## Default Invocation

```bash
python scripts/find_anime_release.py "TITLE" --tier browse --include-magnet --legal-ok --json
```

Add only explicit constraints: `--season`, `--episode`, `--whole-season`, `--min-gib-per-episode`, `--max-gib-per-episode`, `--want-zh`, `--require-zh`, `--release-group-hint`, `--include-page-link`, or `--latest`. Use `--refresh-cache` only when the user asks to check again now or provides a current Nyaa page/screenshot contradicting the report. Use `--include-specials` only after the user chooses a special/OVA instead of a regular episode.

- Use `--require-zh` only when the user explicitly asks to find a release **with Chinese subtitles**, including wording such as “找有中文字幕的资源”, “要求/必须/强制中文字幕”, “要简中/繁中”, or an equivalent hard condition.
- Use `--want-zh` for soft wording such as “中文字幕优先” or “有中文更好”. It remains a same-quality tie-breaker and does not trigger detail-page work.
- Use neither flag for ordinary title-only, episode, quality, size, stability, magnet, or page-link requests. Do not run the strict subtitle branch merely because the title is Chinese or a prior request required subtitles.
- Add `--release-group-hint NAME` only when the user explicitly supplies that group clue in the current request or relevant nearby context. It is a strict-search hint, never a work alias, quality guarantee, or learned default. Never invent a group hint from examples, test fixtures, or unrelated searches.

`--search-title NAME` is an internal handoff for a verified English/romaji title found by the bounded web fallback. The user never needs to provide it. A request containing multiple tracked titles may be passed intact: the script detects them before resolution and returns one `batch` report with an independent result per work. For multiple untracked works, invoke each separately.

## Conversation and Intent

- Inspect the nearest relevant turns first. If exactly one work/version is established and the new request changes only quality, episode, subtitle, stability, or link type, reuse it.
- For a nickname, character catchphrase, or meme-like shorthand, let the high-level script consult `references/anime_nickname_aliases.json` before declaring it unknown. Normalize obvious mainstream references to their canonical work and search that work.
- Separate work identity from Nyaa search names. First establish the exact work/version; only then look up its tracked state and release titles.
- If the report is `needs_web_resolution`, do one bounded `web.search_query` pass before asking: at most two targeted queries from `diagnostic.suggested_queries`. Prefer the Bangumi subject page, an official site, or another authoritative anime catalog. Extract at most two verified English/romaji release titles and rerun the same command once with repeated `--search-title NAME` arguments.
- If the bounded web pass finds no new title, use `diagnostic.provisional_status` when present; otherwise report that the work identity could not be resolved. Do not loop, search releases manually, or call a Chinese-title Nyaa query.
- Spend this small web-search budget when it is likely to avoid a needless clarification or a wrong work. Do not turn it into broad release hunting, and ask one concise clarification only when the web result remains genuinely ambiguous.
- Let the high-level script check local airing state before asking about franchises or versions. A unique tracked state hit is authoritative even when the input is a broad franchise shorthand; ask one concise question only when the structured report remains ambiguous after recent-context and bounded-web resolution.
- Explicit `--episode` wins. `--latest` means latest regular episode, not a special. A title-only request for a tracked airing show means its `next_episode`.
- If a tracked request supplies only a season, or the user replies with a season while resolving an ambiguity, keep that same `next_episode` and call the high-level script with `--season SNN`. A season change is not a request to ask for an episode or to browse a whole season.
- For an old/completed or otherwise untracked TV/TV_SHORT/ONA, a title-only request without an episode defaults to one complete season package. If authoritative metadata confirms exactly one mainline season, infer `S01`; otherwise use the season from the request or resolved work identity. Only return `needs_season_confirmation` when a genuinely multi-season or unknown-scope work remains unresolved. Never reinterpret the request as an arbitrary single episode, OVA, or side story.
- Track only current/still-airing TV, TV_SHORT, or ONA. Never create persistent aliases/progress for old shows, movies, OVAs, specials, or completed titles. A technical RSS/schedule cache is not watch history.
- The nickname registry is title-resolution data, not watch state. Add a verified mapping after a real miss; never use it to imply a user is following an old work.

## Search Pipeline

1. Resolve the exact work, then look up its state by stable Bangumi/AniList ID or alias.
   - A complete tracked record with `search_titles` is the fast path.
   - For a Chinese title or incomplete tracked record, the script queries Bangumi v0 and reads `infobox` aliases; AniList then supplements schedule and mainline metadata.
   - Chinese input is for identity/display only. Without a reliable English/romaji `search_titles` entry, stop as `needs_web_resolution`; never query Nyaa in Chinese and never call that a resource miss.
   - Persist ordered `search_titles`, `verified_search_titles`, `bangumi_id`, and `anilist_id` only for tracked current shows. Promote the query that actually produced the selected release.
   - A string that mentions two tracked works is never a valid alias. The script removes such polluted aliases and auto-batches the request instead of sending the combined string to Bangumi.
2. Fetch raw RSS candidates using at most two high-value titles. Parse season, Decimal episode number, and kind independently: `regular`, `special`, `batch`, or `unknown`.
3. Apply exact target/season and hard quality filters before ranking. Subtitle signals are same-quality tie-breakers only.
4. For `season_batch`, keep only packages that cover the complete target season. Verify a bounded set of high-ranked candidates from their Nyaa file lists and exclude extras. Named tiers use the regular episodes' average size plus the absolute `1 GiB` per-file floor; explicit min/max constraints remain strict per file. Prefer a qualified exact-season package; only then accept a qualified multi-season collection containing the target season.

The parser recognizes `S04`, `Season 4`, ordinal seasons, Roman numerals, Chinese/Japanese season labels, common episode ranges, and multi-season package notation. Decimal episodes, SP, OVA/OAD, OP/ED, recap, and bonus material are specials. If AniList confirms one mainline season, a matching `TITLE - 02` inherits that sole season; related side stories remain separate works. Multi-season titles without season evidence stay visible as `needs_confirmation`.

Only when candidates are genuinely ambiguous to parse may the ordinary path make one targeted RSS fallback query. Do not add manual aliases, broad web searches, or detail-page fetches after a conclusive ordinary report. The explicit `--require-zh` branch below is the only subtitle-specific exception.

## Explicit Chinese-Subtitle Branch

Run the same high-level script with `--require-zh` and every stated episode/size constraint. This branch alone may spend the extra search and detail-page budget.

1. Keep the normal verified Latin queries, then let the script add bounded CJK, accent-folded, distinctive-token, and optional release-group-hint queries. Search Anime - All so Non-English-translated releases are included. This handles naming differences such as `Jaadugar` / `Jādūgar` and simplified/traditional release titles without changing ordinary searches.
2. Apply exact work, season, regular episode, and hard size/source filters before subtitle verification. Strict mode requires a canonical/verified search-title work match; an `unknown` work match is never auto-selected and is returned for confirmation without wasting detail fetches.
3. Inspect qualified Nyaa detail pages in ranked batches of five. Continue until one reliable Chinese result is found, every qualified candidate has been checked, or the total 30-second detail budget is exhausted. Do not classify unchecked candidates as subtitle failures.
4. Accept Simplified and Traditional Chinese equally. Require detail-page evidence such as Chinese, Simplified/Traditional Chinese, `CHS`, `CHT`, `zh-CN`, `zh-TW`, `zh-Hans`, `zh-Hant`, `简体/簡體`, `繁体/繁體`, `简中/繁中`, or `中文`. A Chinese-tagged `.ass`, `.ssa`, `.srt`, `.vtt`, or `.sup` file is direct evidence. A `[CHS]/[CHT]` video filename is valid when the same detail page identifies the subtitle mode, such as `HardSub`, `SoftSub`, 内嵌, 内封, or 外挂.
5. Reject `MultiSub` alone, group reputation, regional-source inference, a title tag with no subtitle context, Chinese audio by itself, explicit negative text such as `Chinese subtitles: None`, and any page whose detail fetch fails. Do not spend extra searches merely to disprove the low-probability Chinese-audio-only case; just avoid treating it as positive subtitle evidence.
6. A strict success must include the exact title, page-reported size, seeders, Nyaa detail URL, full `magnet:?` value when requested, and verified subtitle evidence. Return `subtitle_unqualified` only after every qualified candidate was checked successfully and none had Chinese. If the budget expires, a fetch fails, a detail URL is missing, or candidates remain unchecked, return `subtitle_check_incomplete` instead. Both statuses output no magnet and do not advance progress.
7. If the user supplies a current page/screenshot or a prior-episode group clue that contradicts `subtitle_unqualified`, do one focused browser check of that exact group/work/episode and its detail page. Do not broaden into an unbounded manual hunt.

## Quality Tiers

Use exactly these three user-facing names. Keep the English values only as internal CLI identifiers:

- **轻量观看** (`browse`): single release size, or complete-season regular-episode average, `1-2 GiB`; never accept an ordinary regular file below `1 GiB`, and prefer about `1.5 GiB`.
- **普通观看** (`watch`): single release size, or complete-season regular-episode average, `2-4 GiB`.
- **高画质** (`premium`): single release size or complete-season regular-episode average at least `6 GiB`, or a verified BDMV, remux, or comparable lossless source.

Normalize `随便看看` and `随便看` to **轻量观看**; normalize `一般画质`, `普通画质`, and `中等画质` to **普通观看**; normalize `极致画质`, `极致`, `最高画质`, and `顶级画质` to **高画质**. When no quality wording or explicit size bound is present, default to **轻量观看**. Relative wording such as “画质高一点” is not a tier: use an accompanying explicit size floor, or ask one concise clarification before searching. The `4-6 GiB` gap belongs to no default tier; use it only when the user explicitly gives that custom range.
- Do not reduce any tier floor because an episode is short. For a named-tier season package, use the detail-page file list, exclude OP/ED/SP/OVA/sample files, require every ordinary regular file to remain at least `1 GiB`, and classify by the remaining files' average. If the user explicitly gives `--min-gib-per-episode` or `--max-gib-per-episode`, apply those bounds to every regular file instead. Total-size division is only an early impossibility check, never final proof.
- If an ordinary or `--want-zh` **普通观看** (`watch`) request has no `2-4 GiB` candidate and the user did not give a custom size floor, automatically retry the same target as **轻量观看** (`browse`). Label a successful `1-2 GiB` result as a **轻量观看降级结果**, never as **普通观看**. If a qualified `2-4 GiB` result exists, lack of confirmed Chinese must never trigger this downgrade.
- For explicit `--require-zh`, when **普通观看** has no result satisfying both quality and verified Chinese but **轻量观看** does, return `needs_quality_fallback_confirmation` without a magnet and ask whether to downgrade. Only after the user agrees, rerun as `--tier browse --require-zh`. Never return anything below `1 GiB`.
- A **高画质** request may automatically retry once as **普通观看**. It must never continue to **轻量观看** in the same request. A direct **普通观看** request may retry once as **轻量观看** under the rule above.
- For a complete-season **普通观看** request, if both ordinary and light tiers fail conclusively but a complete high-quality package passes, return `needs_quality_upgrade_confirmation`. Show only its source type, total size, episode count, and seeders; do not expose a page or magnet until the user agrees and the command is rerun as `--tier premium`.
- An explicit `--min-gib-per-episode` is a pure lower bound and removes the named tier's upper limit; pair it with `--max-gib-per-episode` only for an explicit range. Never call a smaller or oversized release qualified when that explicit bound exists.
- For `--want-zh`, target episode, hard floor, and requested tier outrank subtitle signals and seed count. For explicit `--require-zh`, verified Simplified or Traditional Chinese becomes an additional hard filter after work, episode, and size. Only downgrade premium when no viable premium release exists or all premium swarms are effectively dead.
- Never cross below `1 GiB/集` unless the user explicitly supplies a lower custom minimum. Do not display, ask about, or expose the magnet of a candidate rejected by that hard floor.

## Result Handling

- `found`: send `reply_text` verbatim. Ordinary replies contain the complete name, size, seeders, subtitle signal, and requested magnet. A `--require-zh` reply additionally contains the verified detail-page evidence and Nyaa URL.
- `batch`: require the top-level `output_contract.ready=true` and `rendered_count=result_count`, then send the top-level `reply_text` verbatim. It already renders both completed and unavailable children. Never merge titles, episodes, progress, or magnets between children.
- `output_incomplete`: a required output field is missing. Do not claim success, advance progress, or print a label such as `磁力链接` without its value.
- `no_rss_candidates`: no raw RSS candidate was returned after a previously verified search title or after the one bounded web-title retry.
- `needs_web_resolution`: either no reliable Latin release title exists, or two unverified authoritative aliases returned no RSS candidates. Run the bounded web-title handoff once; do not ask the user or search Nyaa in Chinese first.
- `no_nyaa_release_for_target`: the requested regular episode has no matching Nyaa release. Never return an earlier episode as the latest.
- `release_unqualified`: releases exist for the target but fail the stated size/quality range. For a single-episode search with a hard upper bound and `diagnostic.above_max_count > 0`, send `reply_text` verbatim: it says the current range has no qualified release but a higher-range release exists, without exposing its title, size, page, or magnet. Otherwise say the range is unqualified normally. Use `observed_target_max_gib` rather than claiming a maximum from a filtered subset.
- `no_complete_season_release`: no verified package covers every regular episode in the target season. Send `reply_text` verbatim; do not substitute a single episode, special, or partial package.
- `season_check_incomplete`: plausible season packages exist, but a file list, coverage, or per-file size could not be verified. Send `reply_text` verbatim and expose no magnet.
- `needs_season_confirmation`: an old/untracked mainline work defaults to a complete season, but the exact season is unresolved. Send `reply_text` verbatim, ask for the season, expose no magnet, and do not search Nyaa until the user answers.
- `subtitle_unqualified`: every size-qualified target release was checked successfully, but none has detail-verified Simplified or Traditional Chinese subtitles. Output no candidate magnet and leave progress unchanged.
- `subtitle_check_incomplete`: the 30-second budget expired, a detail fetch failed, a detail URL was missing, or qualified candidates remain unchecked. Say the inspection is incomplete; never turn it into “没有中文字幕资源”, output a magnet, or advance progress.
- `needs_quality_fallback_confirmation`: a hard-Chinese **普通观看** request has only a verified-Chinese **轻量观看** fallback. Send `reply_text` verbatim, expose no magnet, and wait. If the user accepts, rerun the same target as `--tier browse --require-zh`.
- `needs_quality_upgrade_confirmation`: ordinary and light complete-season searches failed, but a verified high-quality package exists. Send `reply_text` verbatim, expose no page or magnet, and wait. If the user accepts, rerun the same title and season as `--tier premium`.
- When an ordinary JSON `quality.fallback` is `found`, label the returned release as **轻量观看降级结果**. Never call it **普通观看**.
- `needs_confirmation`: show at most two raw choices with parsed regular/special identity and ask which one the user means. Do not advance progress.
- `latest_unresolved`: a highest observed regular release may be shown, but say official latest status could not be verified. Do not claim it is latest or advance progress.
- `not_aired_yet`: say so directly and do not search backward.

On a successfully found integer regular episode, advance `latest_known_episode` and `next_episode`. A current-airing strict search may create or retain a `tracked_waiting` identity and target after `subtitle_unqualified`, `subtitle_check_incomplete`, or downgrade confirmation, but must not advance the episode. Never advance for specials, unknown candidates, failed quality filters, or an unavailable next episode. Delete the tracked show only on a reliably confirmed final regular episode or when the user says they finished it.

Before replying, enforce `output_contract`: when magnets were requested, every `found` child must have `ready=true`, `missing_fields=[]`, and one full `magnet:?` line in `reply_text`. If this check fails, report the structured error instead of improvising a response.

## References

- Read `references/quality-ranking.md` for batch math, downgrade decisions, subtitle disputes, or ranking diagnostics.
- Read `references/airing-watch-state.md` for watch-state repair, latest/next behavior, or final-episode deletion.
