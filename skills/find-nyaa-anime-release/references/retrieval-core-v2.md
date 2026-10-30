# Retrieval core v2

The default workflow is now [Agent review of full evidence](agent-review.md).
This reference describes the retained compatibility resolver and specialized
movie/batch verification. Its scores, query planning and filtered summaries are
advisory, not the primary discovery or selection authority.

Use for latest/exact ambiguity, interpreting a report, maintaining parsers or replaying failures.

## Decision boundaries

Resolve the immutable local work/season/part identity first → validate provider bindings → plan broad/exact queries → retain raw rows → interpret title spans and structural evidence → confirm target → evaluate quality → Agent review → refetch the reviewed ID's detail → deliver only if requested and qualified. Provider IDs and search aliases cannot merge local records. See [architecture-v3.md](architecture-v3.md) for the current workflow/state boundary; [architecture-v2.md](architecture-v2.md) describes retained resolver internals.

Aniparse 2.0.0 provides hypotheses through `identity_adapter.py`; it is not the identity authority. The adapter masks known full-title spans and records episode positions, seasonal evidence and conflicts. A title number such as `20 Seiki` does not become episode 20. Weak interpretations never inherit another candidate's explicit evidence. A lower, excluded conflict does not block a confirmed higher episode; an unresolved plausible higher episode does.

Regular releases exclude specials, decimal episodes, previews and batches. Movie and season-package entrypoints retain their own checks. Source-numbering conversion requires both `--source-numbering` and `--target-numbering` and one unambiguous, source-stamped range. Missing mappings are unresolved; no guessed offsets.

Latest is determined before size/subtitle eligibility or candidate pinning. If episode 10 exists but fails the floor, keep target 10 and its rejection; do not select episode 9. A detail failure does not erase an already established target. A conflicting newer detail causes latest to be reconsidered.

## Chronological discovery before filtering

For an eligible current/latest search, use a verified work-identifying title rather
than a franchise-wide word or guessed season suffix. Inspect the original first
page in newest-publication order. The existing native client supports this directly:

```python
from nyaa_client import NyaaClient, parse_listing
page = NyaaClient().fetch_listing(
    verified_title, "1_0", "0", 1, 20, sort="id", order="desc"
)
rows = parse_listing(page)
```

Run from the skill's scripts directory or add it to the import path. This is a
read-only listing request using the existing verified transport. Read every row's
full title, ID, size, publication time and seeders in that page; inspect relevant
detail evidence after identifying plausible target candidates. Reuse equivalent
complete raw results already obtained instead of fetching them again.

The CLI automatically chooses size sorting when `--episode` is supplied, even in
discovery mode. Check the reported ordering; do not describe it as chronological.
The discovery `candidates` summary may exclude season mismatches before display,
while `search_run.raw_candidates` retains them. Review plausible mismatches against
the actual work and numbering evidence. Do not change a locked identity to fit a
candidate. If the existing verifier cannot represent the established numbering,
report that limitation rather than absence or bypassing verification.

## Reports and Agent use

`report_version: 2` adds:

- `search_run`: query plan, timestamped actual requests, cache/network failures, complete raw evidence, query/page scope and coverage notes. `completeness` describes the attempted scope, not every historical publication on the site. RSS is a bounded recent window.
- `search_run.identities`: per-ID parser hypotheses, spans (offsets in NFKC-normalized title), work match evidence/IDs, effective season, conflicts and status. `confirmed` here is program evidence, not a claim that an Agent has reviewed it.
- `target_decision`: observed and confirmed release episode, basis and unresolved/conflicting IDs. Unresolved IDs are review material, not necessarily blockers for an already higher target.
- `search_run.eligibility`: explicit size rejection, quality-passed/detail-pending, review-needed, outside-target or qualified state. Pending is not a confirmed rejection.
- summary counts/truncation flags. Raw rows are not truncated; duplicate site IDs merge query hits, equivalent hashes deduplicate selection, and raw audit rows retain `dedup_key`/`duplicate_of` so originals remain inspectable.

Legacy fields remain projections. Do not infer “only E07 exists” from two summary choices. Use raw title evidence and target decision; separate official schedule failures (including 403) from search failures and quality rejection.

Compatibility inspection (read-only):

First check [completion.md](completion.md). Completed delivery returns before Nyaa;
a confirmed finished season with a missing finale performs an exact-finale search,
which does not claim to establish latest from a broad release scan.

```powershell
python scripts/find_anime_release.py "TITLE" --latest --want-zh --no-state-update --json --explain
```

Regular-episode delivery uses the reviewed v3 commands in
[agent-review.md](agent-review.md), not an enqueue command with only a candidate ID.
Keep the accepted tier and original subtitle policy throughout validation and
delivery. An ID pin does not replace work, latest, quality or detail evidence.
Recover an interrupted delivery by its original operation ID. For maintenance
inspection, always omit enqueue and add `--no-state-update`.

## Movie and whole-season finalization

Use the raw evidence tool and model-led selection for these modes too. Keep a short
selection record with work/version, selected ID, numbering or coverage, key evidence
and search scope. For a package, assess the **entire file list together** before
accepting or rejecting coverage:

- Compare the release title, parent directories and every video basename. Identify
  the shared naming pattern and separate season/episode labels, episode titles,
  resolution, codec and other technical numbers.
- Map each regular video to its season and episode using that context. Check the
  resulting set against the independently verified expected episodes; explicitly
  account for missing numbers, duplicates, alternate encodes, other seasons and
  extras. Ten videos alone do not prove that episodes 1 through 10 are present.
- When one file parses differently from its neighbours, inspect its full name and
  matching pattern before excluding it. For example, E01, E02, E03.021, E04 ... E10
  in matching S02 files can indicate episode 3 with a numeric title, rather than
  episode 3.021. Corroborate with the detail description or official episode titles
  when needed; continuity is supporting evidence, not permission to invent an
  episode or reinterpret a genuine decimal special.
- Record the episode-to-file mapping and the evidence resolving any outlier in the
  selection record. If context remains contradictory, report the exact ambiguous
  file instead of declaring the whole season absent or complete. If Agent evidence
  conflicts with the validator, retain that diagnosis for repair and revalidation;
  neither silently skip the file nor bypass the validator.

Use [package-review.md](package-review.md) to draft, audit and deliver a season
or movie with its original policy and exact episode-to-file mapping. The retained
`search_nyaa_releases.py --candidate-id` reports are read-only discovery diagnostics;
they are not submission authorization. Single regular episodes use the reviewed
v3 entrypoint. Legacy pin-only enqueue is rejected with `reviewed_delivery_required`.

Never hand a raw magnet to `qbittorrent_submit.py` or import `submit_magnet` to work
around a failure. Both desktop and Web API add paths require a process-local
capability issued after validation. Preserve original operation/hash and policy
on recovery; a serializable report or `passed:true` cannot manufacture a capability.


## Offline metadata

`data/identity_catalog.json` is an AOD 2026-27 subset for the known tracked IDs at installation. Its source update is 2026-07-04, not a current airing snapshot. Existing reliable identity remains primary. Records, original subset evidence and license retain source/version/hash/update information. It is not automatically refreshed and cannot prove availability.

`offline_identity.py` imports AOD JSON and Anime-Lists XML; `--merge-with` joins only exact AniDB IDs. It supports explicit regular-season start/end/offset mappings, not implicit default seasons, unmapped offsets or special-season maps. Unsupported mappings remain absent. `--offline-catalog PATH` supplies a reviewed catalog. No fuzzy title merges or relation-to-alias conversion.

Anime-Lists importer is implemented and fixture-tested, but no upstream dataset/code is bundled: a redistribution license was not found in the examined repository. Do not silently adopt an unlicensed dataset. See [third-party-notices.md](third-party-notices.md).

## Regression and rollout

Run `python -m pytest tests -q`, then `benchmark_retrieval.py` against `tests/fixtures/retrieval_cases.json` and `tests/fixtures/historical-cache.json`. Keep legacy and Anitopy only as offline baselines. Dependency versions are fixed in `requirements-parsers.txt`; package source and original licenses are shipped unmodified under `scripts/parser_dependencies`.

The recovered ordinary cache has 129 unique IDs, not 129 guessed reconstructions. The larger cache also contains separate Chinese/other-work lanes. Labels cover all 129 ordinary rows plus constructed boundary cases. Report wrong matches, missed matches and review-needed separately, not just pytest totals. Raw libraries and the adapter have different responsibilities; their extraction counts are not end-to-end accuracy measurements.

Never change a label to match parser output. Known failure cases must pass, confirmed outputs must not contain wrong work/season/episode/specials, and normal labeled formats must not regress. Keep the existing production parser if those gates fail. Read-only online validation uses `validate_retrieval_run.py` with isolated state/cache and an enqueue prohibition, then manual raw-title comparison. Recheck the deployed file hashes and preserve a recoverable backup.
