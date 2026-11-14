# Reviewed seasons and movies

Use complete listings/details from `watch.py discover` and `watch.py detail` and
the managed workspace described in retrieval-workflow.md. Do not create a regular
tracking record for a completed package or a movie. Quality comparison uses only
the release detail pages and their file lists, not downloaded samples or external
reviews. Independently establish the work and expected episode count as before.

## Draft and review

When using `search_flow.py`, pipe the scope below directly to `start --scope-stdin`
using the PowerShell example in search-flow.md. Then use `details` and `finish`;
skip the manual draft/read/write commands below. Its displayed file IDs support
`file_refs` for episode files and `file_ref` for exclusions, with AI-supplied
episode mapping/reasons and candidate-local evidence `refs`.

Save the independently verified scope as JSON in the run directory:

```json
{"title":"VERIFIED TITLE","kind":"season","season":"S01","episodes":11,
 "reviewed":true,"source_url":"OFFICIAL_OR_BROADCASTER_URL",
 "evidence_text":"Inspected evidence of this work and its complete episode count"}
```

For a movie use `kind: movie` and `episodes: 1`. These are Agent-reviewed identity
facts, not a filename guess. Then create the incomplete review using the actual
requested policy (the example is premium with soft Chinese preference):

```powershell
python scripts/package_release.py draft --scope RUN_DIR/scope.json --listing RUN_DIR/listing.json --detail RUN_DIR/detail.json --tier premium --want-zh --output RUN_DIR/package-review.json
```

Read the complete file list together with the title and description. Fill:

- `selection.work_reason` and `work_quotes`: scope/identity reasoning and exact
  detail evidence. Account for source/local season numbering differences.
- `selection.episodes`: one entry for each target episode, with `episode` (1-based),
  `files` (exact video paths), `reason`, and exact `quotes`. For a movie use episode
  1. Multiple streams for one episode require a verified BDMV layout; do not sum
  alternate encodes to reach a size floor.
- `selection.excluded_videos`: every other video, each with `file`, `reason` and
  `quotes`, explaining extras, other seasons or alternate encodes. Every video must
  be accounted for exactly once. Episode mapping is an Agent semantic decision;
  count alone never proves coverage.
- `selection.subtitle_quotes`: actual subtitle language evidence, never MultiSub
  alone. For explicit audio/source requirements pass `--require-audio VALUE` /
  `--require-source VALUE` and provide `selection.requirement_evidence` entries
  with matching `kind`, `value`, `reason` and detail `quotes`.
- `quality_policy` and `quality_comparison`: follow agent-review.md. Keep the
  requested policy unchanged. Missing picture evidence means `unknown`, not a
  guessed advantage from size or codec.
- `selection.source_exception`: normally null. For premium only, a verified
  original source may use `{type: "bdmv"|"remux", reason, quotes}`. BDMV requires
  disc playlist/stream structure and an explained episode mapping; Remux requires
  detail evidence that the video was not re-encoded. A title label is insufficient.
  Explicit episode-size bounds disable this exception; movie total bounds remain
  hard. Source eligibility does not establish superior picture quality.

Set `reviewed:true` only after the Agent has read and completed the review.

The comparison shape is `{"result":"unknown","reason":"EVIDENCE-BASED REASON",
"limitations":"WHAT THE PAGES DO NOT ESTABLISH","alternatives":[]}`. Other results
are `comparable`, `only_eligible`, `clear_advantage`. Each actual alternative needs
`detail_report`, `relation`, `reason`, `quotes`; `relation: better` means the selected
resource is better. `clear_advantage` also needs `selected_quotes` and a comparative
alternative. Fill actual evidence, never copy placeholder conclusions. These
fields share the single-episode schema; routine review does not require reading
the validator's Python source.

## Audit, deliver and recover

Use identical policy arguments for drafting, auditing and delivery. Movies default
to a 10 GiB minimum; `--min-total-gib` / `--max-total-gib` express explicit bounds.

```powershell
python scripts/package_release.py deliver --review RUN_DIR/package-review.json --tier premium --want-zh --legal-ok --enqueue-qbittorrent
```

For link-only requests or catalogue choices, use `audit --review ...` with the
same policy instead. Do not routinely audit and immediately deliver: delivery
already validates current details, hash, original policy, per-episode files and
comparison citations. It then issues an in-process capability and calls the
configured desktop or Web API adapter. Do not pass a magnet to qbittorrent_submit.py
or import its submit function as a workaround; these paths reject missing validation.
Validation failures stop before a client add. Diagnose the failing condition;
network failures do not permit a manual bypass or a lower tier.

The default `.package-deliveries/OPERATION_ID/operation.json` beside the tracking
state stores the original request, policy, review and receipt independently of
regular-series progress. Pending evidence is copied beside the journal so temporary
workspace cleanup cannot erase recovery inputs. To recover:

```powershell
python scripts/package_release.py recover --journal JOURNAL_PATH
```

Recovery first checks the exact original hash. Accepted work finishes without a
new add; unaccepted work must pass fresh validation under the original policy.
Missing/stale/changed review evidence requires re-review and never a substitute
hash or a new lower-policy operation. Preserve pending journals. Do not delete
downloads or rewrite periodic schedules as part of package delivery.

To refresh stale/changed evidence explicitly, create and review a fresh manifest
for the same scope/candidate/hash, then use `recover --journal JOURNAL_PATH --review
NEW_REVIEW`. Original policy remains binding. An incomplete historic policy needs
`--original-policy POLICY_JSON` with all original fields, recovered from the user
request, never inferred from permissive defaults. If the original scope or policy
cannot be recovered, stop that operation for review. `--qbittorrent-save-path`
on initial delivery is saved for both adapters and subsequent recovery.
