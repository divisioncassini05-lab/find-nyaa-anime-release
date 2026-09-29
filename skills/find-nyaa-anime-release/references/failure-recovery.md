# Failure recovery

For [full-evidence review](agent-review.md), `discovery_changed` or
`candidate_details_changed` means read the new evidence and revise the review.
`coverage_review_required` and `latest_unresolved` mean finish reviewing, not
narrow the query until uncertain rows disappear. Compatibility exclusions alone
do not prove absence.

Use this after an unsuccessful stage. Preserve originating subtitle, quality, size, work/season/episode, and automatic-download intent. A retry reason, previous answer, or Chinese display title never adds `--require-zh`.

## Decide what failed

| Evidence | Meaning and next action |
| --- | --- |
| Identity or season unresolved | Verify independent titles/metadata; ask only if a real work/version choice remains. No download or timed retry. |
| `identity_conflict` | Keep the locked work/season/part. Inspect `error_detail`, `stage_errors` and `repair_evidence`. The program permits one independently corroborated repair; read-only checks only propose it. If provider scopes disagree, inspect an official page and use `--identity-evidence` (architecture reference), or report ambiguity. Never directly rewrite/merge JSON by provider ID or aliases. |
| `tls_certificate_verify_failed` | Inspect trust chain, proxy and execution context. Keep certificate and hostname verification enabled. If the execution tool indicates a sandbox-related network failure, use its approval mechanism for the same read-only request in the normal environment. Do not repeat the unchanged failing context, infer site downtime/resource absence, or schedule a transient-network retry. |
| Official future date, schedule gap, or part boundary | Report the date/boundary; stop without Nyaa search or progress writes. |
| Query/network failure or incomplete scan | Search coverage is incomplete, not an empty result. Inspect classified transport attempts; do not stack an identical resolver retry after its automatic recovery is exhausted. |
| Complete ordinary search with no matching target | No target found in that search scope; use the bounded supplemental lane below. Do not infer that the episode has not aired. |
| Target candidates exist but fail size/quality or explicitly required subtitles | The episode has a release, but none checked qualifies. Preserve the episode, report the actual rejection and finish the bounded supplemental lane. Never return an older episode. |
| Detail inspection incomplete | Use one distinct eligible backup; after failure report incomplete verification, not absence. |
| Qualified resource found; client rejected/failed | `available_enqueue_failed`. Keep the verified candidate; diagnose client and permissions. Do not restart title search or run the seven-day rescue. |
| Permission/policy rejection | A blocked action, not a network outage. Report the exact action and tool reason; do not promise it happened or bypass it via direct configuration writes. |
| `accepted_state_commit_failed` | The client accepted the exact hash but tracking commit failed. Preserve `.delivery-journal` evidence and rerun the same reviewed hash through high-level finalization; its client-level hash inspection runs before any send. Do not report success or advance progress manually. |

`recovery.retry_basis` describes a possible cause, not permission to create automation. `release_confirmed` is deliberately conservative: an official broadcast schedule alone does not establish a published Nyaa release. For a retry requiring a confirmed latest release, require both `latest_confirmed` and `release_confirmed`; observed candidates alone cannot establish latest when query coverage is incomplete.

## Bounded discovery recovery

The automatic query budgets and supplemental lanes below describe compatibility
tools. With raw evidence, the Agent chooses additional queries/pages from the
actual coverage gap; do not inherit keyword rewriting or fixed shortlist limits.
Transport retry limits and delivery recovery rules still apply.

### TLS and connection recovery

`scripts/http_transport.py` is shared by Nyaa RSS/list/detail requests and torrent-file
downloads. It recovers GETs only, never qBittorrent submissions. A request gets at most
two Python attempts for EOF, timeout, reset, DNS, incomplete-read or HTTP 502/503/504
failures. Attempts share the caller's timeout budget. Certificate failures skip the
identical Python retry. HTTP 4xx and permission failures are not retried or rerouted.

On Windows, an eligible failed GET can use the system `curl.exe` once with certificate
and hostname verification still enabled. This uses Windows native TLS/CA handling,
preserves Python's selected proxy/bypass, ignores `.curlrc`, restricts redirects to
HTTPS, and respects response-size limits. Explicit CA environment overrides disable
this fallback so an operator's chosen trust policy is not silently replaced. If both
backends reject a certificate, report it as a certificate problem and retain progress.
Never add `--insecure`, disable SSL verification, trust a fetched certificate, switch
proxy routes, modify the user's proxy settings, or install a root CA as automatic recovery.

Failures include backend/error codes and recovery success emits `transport_recovery`
to stderr. Record those diagnostics in automation memory (without credentials) so the
next run does not repeat the same blind retries. For persistent TLS failure inspect
the Python executable/OpenSSL version, effective proxy host, configured CA overrides,
and a verified native HTTPS request in the same permitted execution context. A
certificate problem is not evidence the release is unavailable. Permission failures
still require the execution tool's approval flow; the fallback must not bypass it.

Windows Schannel `SEC_E_NO_CREDENTIALS` is reported as
`tls_user_context_unavailable`, with recovery action
`request_approved_execution_context`. Request tool approval for a read-only diagnostic
or the already-reviewed full finalization command in normal user context. Do not
treat this as missing releases, install certificates, or repeat the restricted run.
An exhausted automatic recovery returns `diagnose_exhausted_transport`; repeated
certificate rejection returns `inspect_tls_trust_and_execution_context`, with no timed retry
inferred from either condition.

Transport references: [curl certificate verification](https://curl.se/docs/sslcerts.html)
and [Python SSL defaults](https://docs.python.org/3/library/ssl.html#ssl.create_default_context).

When asked to fix recurring failures, reproduce them or inject the observed error in
tests, change the responsible request path, and verify both recovery and fail-closed
behavior. Report the implemented protection separately from any historical cause
that cannot be established. A one-off successful retry is recovery, not a durable fix.

### Search-level recovery

1. Reuse a completed report and its queried titles. Retry a failed request only if automatic transport recovery was not used or new evidence justifies a changed execution context/configuration. If a cached negative may hide a newly uploaded release, allow one `--refresh-cache` check for the same target and constraints. Do not repeatedly fetch identical aliases or restart a running command. Keep the session ID and poll it. A retry run should refresh its network evidence rather than recycle the preceding negative cache.
2. Check `diagnostic.strict_zh_supplement`: the strict-Chinese core automatically performs one exact-episode supplement after complete ordinary discovery with no qualified release, including subtitle/size rejection. Do not repeat it if already attempted. Otherwise supplement the known Chinese title at the exact regular episode. For hard-Chinese requests, try both Simplified/Traditional search spellings; bundled OpenCC normalization changes query text only and must not become persisted identity or subtitle evidence. Kana titles cannot substitute for a Chinese spelling. Use `--want-zh` unless the originating prompt explicitly requires Chinese. Title trust (`--trust-cjk-title-for-zh`) is only available for explicit hard-Chinese mode; otherwise ordinary identity and subtitle evidence apply. A CJK-only result cannot establish or redefine latest.
3. If no qualified result remains, obtain the failure-only official window:

   ```powershell
   python scripts/find_anime_release.py "USER TITLE" --official-air-date --episode 4 --no-state-update --json
   ```

   Only an eligible currently releasing TV/TV_SHORT/ONA with an exact official episode schedule permits rescue. Run low-level discovery with `--discover --episode N --recent-since DATE --recent-until DATE --current-new-anime`, copying returned dates exactly and preserving all original constraints. The low-level command's `--help` lists the remaining normal discovery arguments. No schedule means no invented/widened window. Require `recent_scan.status == complete` before a negative conclusion.
4. Audit recovered full titles and same-episode alternatives. Verify one ID with the original queries, hard constraints, `--include-magnets --legal-ok`; try one distinct backup only on verification failure. Finalize a qualified automatic result through the high-level resolver with the reviewed `--candidate-id` and `--enqueue-qbittorrent`; use independently verified `--search-title` values if a title bridge is necessary. Do not advance progress during supplementation or rescue.
5. After these bounded stages, stop. State target, inspected scope, rejection or incomplete stage, and the next useful action. Do not claim that no resource exists anywhere. Do not broaden to batches, specials, a different season, or lower the hard floor to obtain a result.

## Client recovery and scheduled retries

The delivery entrypoint performs a Windows execution-context preflight before it
creates a delivery journal or launches qBittorrent. `client_context_required` means
the current token is the Codex sandbox or otherwise unverified; it is not a release
failure and must be recovered by rerunning the complete reviewed resolver in the
approved normal-user context. This preflight prevents the known zero-exit launcher
failure from occurring in the wrong account. The low-level submitter repeats the
guard for direct callers.

- Before evaluating retry triggers, check for persisted completed delivery and
  follow [completion.md](completion.md). A delivered finale with pending scheduler
  cleanup needs cleanup, not another search/download retry. In new or repaired
  lifecycle prompts, parent protection applies only while requested work remains
  unfinished; copy the completion branch into retry children too. Classify children
  by their own declarations and ID, not copied mentions of `retry_child=true`.

- For `startup_exited_without_client` or `handoff_unverified` in a restricted Windows run, inspect the exact hash records and client log, then request execution-tool approval for the **complete high-level resolver command** with the same reviewed candidate and constraints. Starting only the GUI outside the sandbox leaves subsequent IPC/file handoff restricted and is not a context retry. Follow `client_recovery` in the submitter report; it is guidance, not proof of the cause or permission to self-elevate. Allow one complete approved-context retry after the original process finishes. The resolver rechecks acceptance under its lock before submitting and records progress only on acceptance. If this still fails, retain diagnostics and stop; do not repeat unchanged commands or automatically create retries. Record whether full-context recovery succeeded in automation memory so later runs use the working tool context directly, subject to approval. Do not claim the user must import manually before this permitted recovery has been attempted or denied.

- A launcher exit code of zero is not proof a client started or received the torrent. `startup_exited_without_client` is unknown/environmental until diagnosed; never relabel it as a network failure. Use an approved normal-user launch only through execution-tool permissions. Retain exact error codes; missing executable, permission denial and unknown errors are not automatically transient.
- After correcting a client issue, recheck the exact hash and retry that verified submission once using the resolver with the same `--candidate-id`, which advances state only on acceptance. Do not require the video to finish downloading. Do not start parallel enqueue attempts; identical command calls can race with startup and state writes.
- For `handoff_unverified`, inspect the returned hash, backup/profile paths, `acceptance_evidence`, client-process state, and launcher exit/stderr. A running client plus missing matching records is an unverified handoff; IPC/desktop permissions remain a hypothesis until tested. If execution was restricted and those permissions are a plausible cause, use the execution tool's approval mechanism for a normal-user retry of the same reviewed ID and exact episode. Existing download authorization covers the retry's intent, but does not bypass tool permissions. Preserve subtitle and quality constraints; after acceptance let the high-level resolver write progress. Do not repeat unchanged restricted invocations, weaken sandbox settings, or enable Web UI as a workaround. If approval is denied, report the exact action and review reason and retain the qualified candidate with unchanged progress.
- The submitter locks one client profile across processes and rechecks the hash after acquiring the lock. `client_busy` means another submission holds that profile; finish/resume the existing command before a new attempt. Never treat empty command output as an exit, discard returned session IDs, or start a duplicate command while an orchestration cell is still returning its result.
- Create a scheduled retry only when the originating prompt authorizes it and its exact trigger is satisfied. `client_transient` is separate from `network`; a rule mentioning only network/detail/resource availability does not automatically include client startup or enqueue failure. Never schedule for ambiguous identity, already-handled progress, successful/already-present submission, permission rejection, or an unknown/permanent cause.
- For an authorized finite chain, inspect the parent's and children's saved configuration/memory, retain parent ID, target, attempt and original constraints, and keep at most one pending child for that chain. Compute the delay from actual current local time. Enforce the stated attempt cap. A one-time schedule is not proof of automatic deletion; clean up only the exact child when its lifecycle authorizes it. Do not delete an unrelated or old-episode child just to create a new retry.
- Use the app's automation tool to schedule; no raw configuration or shell-scheduler workaround. Only a successful tool response permits “scheduled”. If the tool or memory write fails, say so and retain a concise run record in a permitted workspace if useful; do not claim the canonical memory was updated.
