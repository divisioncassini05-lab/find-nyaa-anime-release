# Local architecture and maintenance

## Agent-reviewed entrypoint

Default discovery uses `inspect_anime_evidence.py` and `anime_release/raw_evidence.py`
to expose complete chronological pages and details without semantic filtering.
The Agent completes the form in [agent-review.md](agent-review.md).

`find_anime_release.py --review PATH` routes through `anime_release/reviewed.py`
instead of the compatibility resolver. The model owns work/episode and numbering
decisions. Code checks track/revision, declared scope, fresh pages, evidence quotes,
size, subtitles and magnet hash, then calls the existing journal/receipt finalizer.
It does not duplicate client or state writers. Other modules below remain available
for existing callers and specialized modes.

The CLI `find_anime_release.py` retains old flags, exits and report projections.
`anime_release/cli.py` converts arguments and renders structured failures.
`workflow.py` orchestrates request → fixed identity → provider evidence → episode
target → verified release → delivery receipt → repository command. Existing parsing,
quality/subtitle and detail/batch policy remains in the retrieval engine; its adapter
receives the fixed identity and cannot write tracking state.

Core types live in `anime_release/models.py`: `ReleaseRequest`, `WorkIdentity`,
`MetadataEvidence`, `TargetDecision`, `VerifiedRelease`, `DeliveryReceipt`,
`StateCommand`, and `WorkflowError`. `legacy_models.py` provides the old mutable
report/projection type; it is not the work identity authority. `state_io.py` is the
manual-command compatibility projection; automated progress uses repository commands.

## v2 JSON

Each element of `shows` has `track_id`, `revision`, `identity_revision` and separate
`identity`, `bindings`, `broadcast`, `progress`, `retrieval`, `deliveries`, `operations`
objects. Unrecognized v1 fields survive in `extra`. `load_state` provides the flat
legacy view without modifying the file; persistent updates use IDs from that view.
Do not construct a replacement whole-state dictionary to update an existing file.

Evidence cache keys include provider, binding ID, local identity token, revision,
season and part. Only raw source evidence is cached. Old merged authority snapshots
are ignored; clearing a cache never removes a track. Cached evidence is validated
again before use. A provider response naming S01 cannot redefine a locked S04.

Reports add `stages`, typed `error_detail`/`stage_errors`, `repair_evidence` and the
local identity token. Use these fields; do not infer the failure stage from text.
Certificate, timeout, permission, identity conflict, detail completeness and client
rejection remain distinct. Nyaa transport retains verified Windows TLS fallback;
metadata POST queries are read-only with bounded retries and classified errors.
No automatic certificate or proxy changes. See [failure-recovery.md](failure-recovery.md).

## Official identity evidence

When a second provider has a different part scope, inspect the official page rather
than coercing its ID. `--identity-evidence PATH` accepts Agent-attested evidence:

```json
{
  "reviewed": true,
  "track_id": "ID_FROM_PROBE_OR_REPORT",
  "identity_revision": 0,
  "source_kind": "official",
  "source_url": "https://official.example/work/season4",
  "checked_at": "2026-09-24T02:00:00+00:00",
  "titles": ["Exact source title Season 4"],
  "season": "S04",
  "part": null,
  "format": "TV",
  "evidence_text": "Source-backed identification of the exact season/part scope."
}
```

Use actual inspected text, source URL and time, not this illustrative domain.
This does not override the provider's own evidence or the locked work; unique
corroboration is still required. Read-only finalization only reports a repair proposal.

## Validation and deployment

Develop in a separate skill copy. Run all tests, the 149 historical labels, raw
provider/RSS/HTML replay, process concurrency and interrupted delivery tests. Replays
substitute network IO only; never pre-mock the final identity/target correctly.
`validate_retrieval_run.py` performs online read-only validation with isolated state
and cache and a client-call prohibition. Test actual `re0` and existing tracks.

Deploy only tested skill files after checking source hashes for concurrent changes,
backing up replaced files, and confirming no write task is running. Migrate only
this skill's tracking JSON with a fresh preview hash. Preserve the desktop app and
all of its data/configuration/cache; do not repack it or change automation schedules.
Recheck deployed hashes and run the installed entrypoints read-only. Real download
submission is not a maintenance acceptance test.
