# Quality, Ranking, and Diagnostics

Use this reference for quality disputes, batch math, downgrade decisions, or diagnostics. Follow SKILL.md for raw discovery and Agent review. All delivery paths preserve the requested tier and constraints; changing tier requires a new explicit user decision.

## Search Budget

The fixed query/page and automatic-fallback details here describe the compatibility
resolver. The default [full-evidence workflow](agent-review.md) uses explicit
chronological pages and Agent-decided coverage. It retains the quality bounds below
without inheriting a top-k reading limit or silently choosing another tier.

- The high-level path uses at most three verified broad query titles. Latest discovery retains episode-free RSS recency queries even when a schedule predicts an episode; exact episodes, complete seasons, premium tiers, explicit bounds and trusted Chinese-title lanes use the bounded HTML size-sorted lane.
- A size-sorted lane reads at most three pages per query and stops on an exhausted page, not on a quality match or floor. The complete collected window is retained before quality decisions. Report the query/page scope and coverage notes; a bounded search does not prove global absence.
- Raw RSS or size-sorted listing items are cached briefly and rescored/reclassified under every new season, episode, and size policy. Final "no result" conclusions are not cached as facts.
- Schedule metadata is cached briefly for latest/next checks. Use `--refresh-cache` for an explicitly fresh check, contradictory current evidence, or the single cached-negative refresh / scheduled retry defined in [failure recovery](failure-recovery.md).
- If no exact target is confirmed, the bounded fallback uses explicit seasonal/episode and bare episode formats. In hard-Chinese mode, a complete but unqualified search also receives one exact-episode supplement with both Chinese script spellings and stable Latin anchors. Queries, the primary rejection, and supplement outcomes remain visible in `strict_zh_supplement` and `search_run`. Conversion generates search spellings only, never new identity aliases or numbering offsets.

## Tiers and Size Floors

These are this user's eligibility bounds, not universal definitions of visual
quality. Passing a size floor is necessary under the applicable policy but is
not sufficient to call a release high quality. Preserve the existing bounds and
documented source exceptions; this preference changes comparison, not the bounds.

```text
轻量观看 (browse): 1-2 GiB per episode, with 1 GiB as a hard floor
普通观看 (watch):  2-4 GiB per episode
高画质 (premium):  at least 6 GiB per episode, BDMV, remux, or comparable lossless source
```

- `随便看看` and `随便看` map to **轻量观看**. `一般画质`, `普通画质`, and `中等画质` map to **普通观看**. `高画质`, `极致画质`, `极致`, `最高画质`, and `顶级画质` map to **高画质**.
- No quality wording defaults to **轻量观看**. Relative wording such as “画质高一点” needs an explicit size floor or one clarification before searching.
- `4-6 GiB` is intentionally outside the three defaults. Apply that range only when the user explicitly requests it.

- Explicit size constraints override tier hard bounds. `--min-gib-per-episode 1` means `>=1 GiB` with no upper limit; add `--max-gib-per-episode` only when the user states a range.
- `--allow-upward-compatibility` is an explicit opt-in for a named tier: keep
  that tier's lower floor hard, treat its upper size as a preference, and
  accept a higher-tier release only when all identity, subtitle, source, and
  stability checks pass. Prefer an in-tier release whenever one qualifies.
  A user-supplied `--max-gib-per-episode` remains a hard cap and disables this
  relaxation; movie total-size bounds are unaffected.
- Do not reduce a tier floor for a short runtime. A 12-minute episode at 514 MiB is below both `watch` and `browse` for this user.
- For a season package, use an authoritative expected episode count and inspect the Nyaa file list. Exclude NCOP/NCED, PV, CM, sample, OVA/OAD, specials, and extras. Every regular file must satisfy the selected tier or explicit per-episode bounds; an average cannot mask an undersized episode. Premium retains its verified BDMV/remux source exemption. Explicit min/max constraints remain strict per file. Total size may prove a package is impossible, but cannot prove it is qualified.
- In discovery output, treat `size_scope: batch_total` as an explicit warning: `size_gib` is the whole package, `per_episode_size_gib` is unavailable, and `requires_whole_season_verification` must remain true until file-list coverage and quality checks succeed.
- A below-floor Chinese-subtitle release must not beat a qualified unsubtitled or multi-subtitle release unless Chinese subtitles are an explicit hard requirement and the user has separately approved a tier downgrade.
- Failed searches do not change tiers automatically, including the compatibility
  resolver. Report the unmet constraint. A user-approved tier change starts a new
  review with its explicit policy; it cannot alter an in-flight delivery operation.

## Ranking

Hard filters happen before ranking:

1. Work, effective season, and exact regular episode.
2. Explicit size bounds or the requested tier range. With upward compatibility,
   only the named tier's lower floor is hard; a higher-tier candidate is marked
   as an upward-compatible result and is considered after in-tier candidates.
3. Any requested audio/source restriction.
4. For a complete-season request: verified regular-episode coverage, the per-file absolute floor, then named-tier or explicit per-file bounds. Prefer exact-season packages before qualified multi-season collections.

Compare eligible releases using only their detail pages and complete file lists,
including existing MediaInfo, source/encoding notes and static comparisons shown
on those pages. Do not download video samples or consult external reviews. Assess
source/master edition, retained detail/grain, compression artifacts, banding and
filtering only to the extent supported by that evidence. Resolution, Blu-ray,
Remux, codec, bit depth, bitrate and file size alone do not prove superiority.
More audio tracks or extras do not improve video quality.

Use a clear evidence-backed picture advantage first. If the apparent difference
is small or the pages cannot establish one, mark comparable/unknown and use:
verified Chinese subtitles, seed availability, an explicit user group preference,
then ascending numeric candidate ID for a stable tie. Do not assume zero listed
seeders proves a dead torrent. More detailed descriptions are not a quality bonus.
Keep unknown evidence explicit; do not invent playback observations.

The old mixed numeric score is deprecated. Size within a valid interval, proximity
to its midpoint, codec labels and resolution labels earn no automatic quality
points. Script ordering is practical inspection priority, never the Agent's final
quality verdict. Explain decisive alternatives in `quality_comparison`, and carry
the unchanged `quality_policy` from draft through delivery. The tier/source
eligibility exceptions do not waive this evidence-based comparison.

## Structured Outcomes

- `release_unqualified` means target candidates were seen and rejected by quality. For a single episode with a hard upper bound, `above_max_count > 0` means the reply should say that the current range has no qualified release but a higher-range release exists; do not expose that release's title, size, page, or magnet. For season packages, report only aggregate rejection counts and never expose rejected titles or magnets.
- `no_complete_season_release` means inspected packages were partial, wrong-season, special-only, or otherwise failed complete regular coverage.
- `season_check_incomplete` means a plausible package could not be verified because its detail page, file list, or file identity remained unavailable or ambiguous.
- `no_nyaa_release_for_target` means no regular candidate matched the target after parsing, not that a regex hid it.
- Partial query failure takes precedence over a negative candidate/quality conclusion: return `network_error` with the surviving rejection diagnostics. A latest discovery with partial query coverage remains `latest_unresolved` and cannot be enqueued.
- `subtitle_unqualified` means every size-qualified candidate was checked successfully and none had verified Chinese subtitles.
- `subtitle_check_incomplete` means the detail budget expired, a request failed, a URL was unavailable, or candidates remain unchecked. Do not state that no Chinese release exists.
- `needs_quality_fallback_confirmation` is retained for reading historical reports; new searches never lower tiers automatically.
- `needs_quality_upgrade_confirmation` is retained for historical reports; a user-requested tier change requires a new review.
- `needs_confirmation` means special/batch/unknown parsing makes a definitive choice unsafe. Present at most two choices and their parsed identity.
- `latest_unresolved` means release-based latest cannot be confirmed due to identity ambiguity or incomplete query evidence. A missing official schedule alone does not imply it. Keep official airing evidence separate from observed resource publication.
