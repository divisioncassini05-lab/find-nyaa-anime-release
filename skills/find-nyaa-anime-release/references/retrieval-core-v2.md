# Retrieval core v2

Use for latest/exact ambiguity, interpreting a report, maintaining parsers or replaying failures.

## Decision boundaries

Resolve a work using reliable IDs and source-backed aliases → plan broad/exact queries → retain raw rows → interpret title spans and structural evidence → confirm target → evaluate quality → Agent review → refetch the reviewed ID's detail → deliver only if requested and qualified.

Aniparse 2.0.0 provides hypotheses through `identity_adapter.py`; it is not the identity authority. The adapter masks known full-title spans and records episode positions, seasonal evidence and conflicts. A title number such as `20 Seiki` does not become episode 20. Weak interpretations never inherit another candidate's explicit evidence. A lower, excluded conflict does not block a confirmed higher episode; an unresolved plausible higher episode does.

Regular releases exclude specials, decimal episodes, previews and batches. Movie and season-package entrypoints retain their own checks. Source-numbering conversion requires both `--source-numbering` and `--target-numbering` and one unambiguous, source-stamped range. Missing mappings are unresolved; no guessed offsets.

Latest is determined before size/subtitle eligibility or candidate pinning. If episode 10 exists but fails the floor, keep target 10 and its rejection; do not select episode 9. A detail failure does not erase an already established target. A conflicting newer detail causes latest to be reconsidered.

## Reports and Agent use

`report_version: 2` adds:

- `search_run`: query plan, timestamped actual requests, cache/network failures, complete raw evidence, query/page scope and coverage notes. `completeness` describes the attempted scope, not every historical publication on the site. RSS is a bounded recent window.
- `search_run.identities`: per-ID parser hypotheses, spans (offsets in NFKC-normalized title), work match evidence/IDs, effective season, conflicts and status. `confirmed` here is program evidence, not a claim that an Agent has reviewed it.
- `target_decision`: observed and confirmed release episode, basis and unresolved/conflicting IDs. Unresolved IDs are review material, not necessarily blockers for an already higher target.
- `search_run.eligibility`: explicit size rejection, quality-passed/detail-pending, review-needed, outside-target or qualified state. Pending is not a confirmed rejection.
- summary counts/truncation flags. Raw rows are not truncated; duplicate site IDs merge query hits, equivalent hashes deduplicate selection, and raw audit rows retain `dedup_key`/`duplicate_of` so originals remain inspectable.

Legacy fields remain projections. Do not infer “only E07 exists” from two summary choices. Use raw title evidence and target decision; separate official schedule failures (including 403) from search failures and quality rejection.

Scheduled workflow:

```powershell
python scripts/find_anime_release.py "TITLE" --latest --want-zh --no-state-update --json --explain
# Agent reviews full titles, conflicting evidence, constraints and same-episode alternatives.
python scripts/find_anime_release.py "TITLE" --latest --candidate-id 1234567 --want-zh --include-magnet --legal-ok --enqueue-qbittorrent --json
```

Use the effective accepted tier and original subtitle policy on finalization. Do not retry an unreviewed enqueue command: it returns `review_required`. A candidate pin is selection intent, not an override of work, latest, quality or detail checks. For maintenance tests, always omit enqueue and add `--no-state-update`.

## Offline metadata

`data/identity_catalog.json` is an AOD 2026-27 subset for the known tracked IDs at installation. Its source update is 2026-07-04, not a current airing snapshot. Existing reliable identity remains primary. Records, original subset evidence and license retain source/version/hash/update information. It is not automatically refreshed and cannot prove availability.

`offline_identity.py` imports AOD JSON and Anime-Lists XML; `--merge-with` joins only exact AniDB IDs. It supports explicit regular-season start/end/offset mappings, not implicit default seasons, unmapped offsets or special-season maps. Unsupported mappings remain absent. `--offline-catalog PATH` supplies a reviewed catalog. No fuzzy title merges or relation-to-alias conversion.

Anime-Lists importer is implemented and fixture-tested, but no upstream dataset/code is bundled: a redistribution license was not found in the examined repository. Do not silently adopt an unlicensed dataset. See [third-party-notices.md](third-party-notices.md).

## Regression and rollout

Run `python -m pytest tests -q`, then `benchmark_retrieval.py` against `tests/fixtures/retrieval_cases.json` and `tests/fixtures/historical-cache.json`. Keep legacy and Anitopy only as offline baselines. Dependency versions are fixed in `requirements-parsers.txt`; package source and original licenses are shipped unmodified under `scripts/parser_dependencies`.

The recovered ordinary cache has 129 unique IDs, not 129 guessed reconstructions. The larger cache also contains separate Chinese/other-work lanes. Labels cover all 129 ordinary rows plus constructed boundary cases. Report wrong matches, missed matches and review-needed separately, not just pytest totals. Raw libraries and the adapter have different responsibilities; their extraction counts are not end-to-end accuracy measurements.

Never change a label to match parser output. Known failure cases must pass, confirmed outputs must not contain wrong work/season/episode/specials, and normal labeled formats must not regress. Keep the existing production parser if those gates fail. Read-only online validation uses `validate_retrieval_run.py` with isolated state/cache and an enqueue prohibition, then manual raw-title comparison. Recheck the deployed file hashes and preserve a recoverable backup.
