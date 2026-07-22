# Quality, Ranking, and Diagnostics

Use this reference only for unusual quality disputes, batch math, downgrade decisions, or a structured diagnostic. Ordinary requests use `scripts/find_anime_release.py` once.

## Search Budget

- The high-level path resolves at most two non-redundant, Nyaa-friendly titles, then fetches RSS with the configured short timeout.
- Raw RSS items are cached briefly and rescored/reclassified under every new season, episode, and size policy. Final "no result" conclusions are not cached as facts.
- Schedule metadata is cached briefly for latest/next checks. Use `--refresh-cache` only when the user explicitly asks for a fresh check or supplies current Nyaa evidence that contradicts the report.
- A single exact fallback query is allowed only when raw candidates are present but their season/episode parsing is uncertain. Never broaden blindly across aliases or browse manually after a conclusive report.

## Tiers and Size Floors

```text
轻量观看 (browse): 1-2 GiB per episode, with 1 GiB as a hard floor and about 1.5 GiB preferred
普通观看 (watch):  2-4 GiB per episode
高画质 (premium):  at least 6 GiB per episode, BDMV, remux, or comparable lossless source
```

- `随便看看` and `随便看` map to **轻量观看**. `一般画质`, `普通画质`, and `中等画质` map to **普通观看**. `极致画质`, `极致`, `最高画质`, and `顶级画质` map to **高画质**.
- No quality wording defaults to **轻量观看**. Relative wording such as “画质高一点” needs an explicit size floor or one clarification before searching.
- `4-6 GiB` is intentionally outside the three defaults. Apply that range only when the user explicitly requests it.

- Explicit size constraints override tier hard bounds. `--min-gib-per-episode 1` means `>=1 GiB` with no upper limit; add `--max-gib-per-episode` only when the user states a range.
- Do not reduce a tier floor for a short runtime. A 12-minute episode at 514 MiB is below both `watch` and `browse` for this user.
- For a season package, use an authoritative expected episode count and inspect the Nyaa file list. Exclude NCOP/NCED, PV, CM, sample, OVA/OAD, specials, and extras; every regular video file must pass the active range. Total size may prove a package is impossible, but cannot prove it is qualified.
- A below-floor Chinese-subtitle release must not beat a qualified unsubtitled or multi-subtitle release unless Chinese subtitles are an explicit hard requirement and the user has separately approved a tier downgrade.
- For an ordinary or soft-Chinese **普通观看** (`watch`) request with no `2-4 GiB` candidate and no user-supplied custom floor, the high-level script automatically retries the same target as **轻量观看** (`browse`, `1-2 GiB`). Label it **轻量观看降级结果**. A valid `2-4 GiB` candidate is never displaced merely because a smaller release has Chinese subtitles.
- For a hard-Chinese **普通观看** request, a verified-Chinese **轻量观看** fallback produces `needs_quality_fallback_confirmation`: show its metadata without a magnet and ask first. After approval, rerun at `browse`; never go below `1 GiB`.
- A high-quality request may retry exactly once at normal-watching quality. A direct normal-watching request may retry exactly once at lightweight quality. Never chain high -> normal -> lightweight in one request.

## Ranking

Hard filters happen before ranking:

1. Work, effective season, and exact regular episode.
2. Explicit size bounds or the requested tier range.
3. Any requested audio/source restriction.
4. For a complete-season request: verified regular-episode coverage and per-file size. Prefer exact-season packages before qualified multi-season collections.

Rank qualified candidates by requested quality, then swarm strength, original audio, an explicit current-request group hint, and finally Chinese/mixed-subtitle signals. In ordinary or soft-Chinese mode, subtitle signals are tie-breakers within the same quality class and never a reason to cross a hard filter. In hard-Chinese mode, verified Simplified or Traditional Chinese is an additional hard filter after work, episode, and size.

## Structured Outcomes

- `release_unqualified` means target candidates were seen and rejected by quality. For a single episode with a hard upper bound, `above_max_count > 0` means the reply should say that the current range has no qualified release but a higher-range release exists; do not expose that release's title, size, page, or magnet. For season packages, report only aggregate rejection counts and never expose rejected titles or magnets.
- `no_complete_season_release` means inspected packages were partial, wrong-season, special-only, or otherwise failed complete regular coverage.
- `season_check_incomplete` means a plausible package could not be verified because its detail page, file list, or file identity remained unavailable or ambiguous.
- `no_nyaa_release_for_target` means no regular candidate matched the target after parsing, not that a regex hid it.
- `subtitle_unqualified` means every size-qualified candidate was checked successfully and none had verified Chinese subtitles.
- `subtitle_check_incomplete` means the detail budget expired, a request failed, a URL was unavailable, or candidates remain unchecked. Do not state that no Chinese release exists.
- `needs_quality_fallback_confirmation` means a hard-Chinese request can only be met by dropping from **普通观看** to **轻量观看**. Do not expose the fallback magnet before approval.
- `needs_confirmation` means special/batch/unknown parsing makes a definitive choice unsafe. Present at most two choices and their parsed identity.
- `latest_unresolved` means an official airing target was unavailable; do not phrase the observed candidate as official latest.
