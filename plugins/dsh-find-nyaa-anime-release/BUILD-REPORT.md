# Build verification: 0.2.8

## Public presentation update: 2026-11-11

- Public display name and page heading are now `dsh-find-anime`; the npm name,
  plugin IDs, Codex installation URL and state locations are unchanged.
- Rewrites the Chinese detail page and bilingual summary; five screenshots use
  the actual panel with fictional, offline fixture records. Screenshot capture
  blocks external requests and rejects configuration writes. No personal data.
- The screenshot manifest ships beside package.json for public market discovery.
  Preview fixtures are not part of the production client bundle.
- Core/distribution Python: 765 passed. DSH/adapter/archive Python: 847 passed.
  Each suite has 3 skips, 1 excluded live test and 15 passing subtests. Both retain
  the existing unknown-live-marker warning. Both UTF-8 skill validators and the
  generated-payload drift check pass. No core or adapter behavior changes.
- Node suite exits successfully (309 test outcomes, including optional skips).
  Production client builds successfully. Five Playwright/Edge screenshots have
  zero page errors and were visually inspected, including the night theme.
- Package/archive verification is performed on the exact release tarball before
  publication. npm bytes and GitHub asset digests are verified independently.
- No local DSH installation, real downloads, account writes or scheduler changes
  are part of this release. Public market submission remains subject to review.

## Previous verification: 0.2.7

## Living ocean integration: 2026-11-11

- Integrates the separately reviewed environment previously omitted from 0.2.6:
  native-frame day/night fauna, social schooling/avoidance, restrained seaweed,
  painted seabed waterlight, marine snow, bubbles and current traces.
- The existing bottom-right floor framing is used for seabed anchors. Both
  paintings, shared panel CSS, actor/seat sources, summoned fish sources and
  every original character asset are unchanged from the published 0.2.6 tree.
  Environmental canvases are isolated in the existing lowest ocean context;
  pointer/focus handling cannot reach them. No new public RPC or user data.
- Core and DSH generated skills remain synchronized without payload changes.
  Core Python plus distribution tests: 765 passed. DSH Python plus archive test:
  847 passed. Both retain 3 skips, 1 excluded live test and 15 passing subtests.
  Both skill validators pass. A first DSH run encountered WinError 5 in the
  unchanged two-process state replacement test; its focused rerun and the full
  DSH rerun passed. This is recorded, not silently treated as a first-run pass.
- Node: 304 passed, 5 optional host/dependency tests skipped, 0 failed. Includes
  native frame selection, species motion, schooling, responsive density, fixed
  terrain anchors, scene-time pauses and actor/checking/reading regressions.
- Built-page browser checks pass at 1440/780/390/320px in both themes: nonblank
  moving water/fish pixels, correct terrain framing and stacking contexts,
  persistent pause, hidden/reduced-motion freeze, theme isolation, unchanged
  content geometry, empty/error states and narrow configuration dialogs.
- The unchanged actual character component also passes its 150px/132px reading
  retreat check: all 16 hidden reopening frames, pause/resume, cleared magic
  and restoration of the original reading. No external requests were observed.
- Source ZIP collection now includes nested client modules; an explicit archive
  regression ensures the new environment sources are not omitted. Runtime
  tarball bytes and source ZIP contents are verified before publication.
- This release does not install over the local DSH profile. It leaves the
  existing npm 0.2.6 installation available for a user-driven update test.
  No logged-in DSH GUI update, real download or Bangumi write is claimed here.

## Previous verification: 0.2.6

## Reading retreat and approved ocean fauna: 2026-11-11

- Combines the accepted local reading triple-click branch with the completed
  local ocean paintings and fauna. No new artwork generation or motion redesign.
- Reading retreat uses the exact accepted close/lift, water veil and hidden
  reopening clips. Original four motion masters, random gestures and checking
  fish remain unchanged. New checks wait for reveal, then complete the original
  reading-to-idle handoff before summoning.
- Background fauna remain separate from summoned fish. Both terrain paintings,
  the sparse day/night species pools and local jellyfish glow come from the
  approved local source. Theme, pause, visibility and reduced-motion behavior
  remain local presentation only.
- Search/quality/subtitle policy, host adapters, download operations, schedules,
  Bangumi writes, public skill payload and user data are not changed.
- Package and lockfile agree on 0.2.6. Installation package name, Codex URL and
  custom-market index URL stay stable. Archive checks compare all shipped bytes
  with this tree; credentials, test caches and personal tracking files are not
  public inputs. Publication and registry integrity are verified separately.
- Offline verification in separate processes: canonical Python 758 passed,
  distribution synchronization 7 passed, generated DSH/adapter/panel Python 846
  passed. Each Python skill suite retained 3 skips, 1 excluded live test and 15
  passing subtests. Both skill validators and reproducibility check passed.
- Node suite: 234 passed, 5 optional host/dependency tests skipped, 0 failed.
  Includes real native bundle registration/shared-React checks and the new
  reading/checking handoff regressions. This is not exhaustive host coverage.
- Actual built-component browser checks passed at desktop 150px and narrow
  132px: settled reading entry, all 16 hidden reopening cels, pause/resume,
  original-reading restore and cleared magic. Ocean checks passed for sparse
  day/night pools, movement, local light, themes, static mode, hidden lifecycle,
  reduced motion, narrow dialogs and unchanged content layout.
- Browser readiness is polled independently of the test-owned animation clock;
  this avoids a parked test RAF blocking decoder readiness. Runtime behavior
  was not changed to satisfy the test.
- These are local component/browser checks, not a logged-in desktop,
  real-download, cloud-write or live scheduler test.

## Previous verification: 0.2.5

## Pre-publication local verification: 2026-11-11

- This report records pre-publication local verification, not remote publication
  or desktop installation. Publication records are maintained separately.
- Integrates the approved checking summon with a stable-idle handoff before entry.
  Checking fish use the upper 70% of the currently visible water area; the limit
  covers the full sprite, including turns and viewport contraction, not only its
  centre. Reading/return/ambient playback must finish before checking owns the actor.
- Includes the approved repaired trace animation and native perspective water
  effects. Removes permanent button chrome from the transparent mascot while
  retaining keyboard focus indication. These are presentation changes, not new
  retrieval, download, scheduling or Bangumi write operations.
- Excludes background fauna, ocean paintings, overlays
  and related background code. The canonical skill and DSH host adapters retain
  their existing behavior; original Codex installation and marketplace URLs stay
  unchanged.
- Offline Python rerun in separate processes: canonical 758 plus distribution
  synchronization 7 passed (765 total); DSH adapter, panel policy and generated
  skill suite 846 passed. Each process retained 3 skips, 1 excluded live test,
  15 passing subtests and the existing unregistered live-marker warning.
- Full Node suite: 223 passed, 0 failed, 0 skipped, including actual Cordis,
  SkillRegistry, Connection and official market-index checks. Existing external
  test-only dependencies were read without installing or changing them.
- Core synchronization reports synchronized with no changed files. Both Codex
  and DSH quick_validate.py checks passed. Package and lockfile agree on 0.2.5;
  dependency versions are unchanged. git diff --check passed.
- Complete Python logs and JUnit XML, Node TAP output, synchronization output and
  validator logs were retained outside the checkout. Temporary roots, Hypothesis
  data and application state were isolated per test process from personal data.
- Main integration browser verification reports a 1280px desktop with a 150px
  character and a 390px mobile layout with a 132px character, including dark
  theme: checking-loop renders, success finishes back at idle, resident fish
  keep moving and no browser errors occur. This is limited integration evidence,
  not a logged-in desktop test or exhaustive result/viewport coverage.
- The handoff suite includes 15 regressions. Final integration makes the handoff
  own the ambient blocker on repeated starts, blocks user greetings while checking
  loads, and pauses the normal offscreen actor while resident fish keep updating.
- Seven component integration regressions cover the actual WhaleMascot loading
  continuation, signal handler, timeline and checking controller together, with
  hooks/canvas/scheduling faked. They include the final loading and missing-geometry
  boundary repairs; this does not replace real-browser acceptance.
- Public-input review includes all intentional checking materials; no new secret
  or personal machine path was found. The two existing local-path matches are
  generic installation/preview examples. Background fauna remain excluded.
- Stable-source client build and the full Node rerun passed after the final
  boundary repairs. Archive verification compares every runtime file with this
  tree and checks the declared source ZIP; actual results and hashes are recorded
  outside the checkout. Earlier local packages are superseded by this stable
  snapshot. No installed-desktop, real-download or cloud-write test is claimed.
  Results below for 0.2.4 and earlier remain historical.

## Previous verification: 0.2.4

## Ambient gestures: 2026-11-10

- Added five reviewed idle/reading gestures, independent continuously timed book
  layer, palm water, and blue-water-to-black-ink effect. Original four master GIFs
  remain byte-identical. No retrieval, download, schedule or cloud behavior changed.
- Full Python regression: canonical 758 + distribution 7 passed; DSH 846 passed.
  Each core suite retains 3 platform skips, 1 excluded live test and 15 subtests.
  Native Node: 131 passed, including the actual DSH Connection adapter tests.
  Tests use isolated paths and synthetic data, not real downloads/cloud writes.
- Effect preview checked 108 desktop/mobile/theme/time samples, ink colour
  progression, book-cover occlusion, empty effect tails, real-time completion and
  pause. Built-plugin Playwright checks also passed all five lazy-decoded actions
  at 150px/132px, continuous book phase, reduced motion and resume, with no browser
  errors. The four-stage browser suite passed three real-time cycles at each size,
  themes, visibility, keyboard control and poster fallback. Runtime/source archive
  contents are checked separately against the final tree before publication.
- Only one extra ambient GIF is decoded at a time. Parent loops continue while a
  gesture decodes; a failed gesture cannot freeze playback. Offscreen/reduced
  motion retains animation phase. Small redraw differences remain in sleeve/chin
  gestures; technical results are not a claim of pixel-perfect artwork.
- Earlier reports below describe their respective releases or local candidates.

## Release verification: 2026-11-10

- Codex/distribution Python: 765 passed. DSH Python including panel policy: 846
  passed. Each retains 3 platform skips, 1 excluded live test and 15 passing
  subtests. Node: 123 passed. Both skill validators and generated-payload checks
  passed. The known unregistered live-mark warning does not affect results.
- The publication rerun exposed an intermittent Windows byte-lock initialization
  race. Removing the pre-lock byte write fixes contention with an empty locked
  file; an explicit regression verifies retryable client_busy rather than a raw
  permission failure. Both distributions contain the same fix.
- Initial sandboxed runs failed on rewritten temporary paths; final suites used
  isolated workspace temporary directories outside that sandbox. No product
  networking or user-machine-specific runtime path was changed for the tests.
- Network-blocked lifecycle simulation passed 29/29 checks. Prior UI checks below
  cover the same built interface; this release pass only adds common Bangumi
  guidance, documentation and the lock fix. Tests never wrote real Bangumi records,
  submitted real downloads or changed personal schedules.
- Runtime tarball and source ZIP are verified against declared inputs before
  publication. Registry integrity, GitHub release assets and the npm-backed index
  are checked separately; a local build is not treated as a successful release.
- The older sections below record their original local-only validation stages,
  not additional independent publication claims.

## Underwater component design: 2026-11-10

- Presentation-only refresh of metrics, tabs, filter and sort controls, inbox and
  library rows, progress indicators, split actions, expanded results and dialogs.
  Pearl-white/sea-teal daytime surfaces and low-luminance nighttime surfaces use
  restrained lilac, coral and amber accents. Backgrounds and mascot are unchanged.
- Grouped plan and downloader forms use the same typography, separators, focus
  rings and control dimensions. Weekday checkboxes retain full-label hit areas;
  account secrets remain password inputs. No RPC, retrieval, download, schedule,
  progress, completion or Bangumi writeback behavior changed in this pass.
- Playwright passed inbox actions, general UI and ocean lifecycle suites, plus
  a new surface suite covering both themes at 1440/800/390/320px. It checks dialog
  bounds, controls, weekday selection and at least 4.5:1 contrast for tested text
  token pairs. Screenshots were inspected for desktop, mobile and dark dialogs.
  The theme tests also check host isolation, reduced motion and layout stability.
- Regression: canonical/distribution Python 764 passed; DSH Python 841 plus panel
  policy 4 passed; Node 123 passed. The full Python runs each retain 3 skips,
  1 live deselection and 15 subtests. A pre-existing unregistered live-mark warning
  remains. The system pytest temp directory was denied; reruns used isolated
  workspace temp directories without changing system permissions.
- Both skill validators and distribution synchronization passed. Browser/account
  tests used synthetic data; no real Bangumi, torrent or user schedule mutation.
  The README screenshot now reflects the component refresh. Local build only:
  no npm, GitHub or marketplace publication, and no personal-state migration.

## Three search scopes: 2026-11-10

- Replaced the task-mode/tracking-mode combination with whole-season package,
  latest regular episode, or all locally unrecorded episodes through the latest
  aired episode. Legacy next-tracked panel plans use latest semantics without
  rewriting personal state. Movie packages retain their existing whole-work path.
- A verified whole-season/movie find completes its one-shot search immediately,
  leaves active-tracking counts, and remains in Completed with separate download
  status. An ongoing authorized delivery is not interrupted; later scheduled
  searches are skipped. No automatic watched-progress write was introduced.
- Missing-episode runs use a read-only deterministic worklist, not a scalar
  high-water mark or Bangumi watched progress. Partial finds and per-episode
  download actions survive; gaps can be delivered after a previously found finale.
  Paused/deleted/blocked plans cannot use that backfill exception. Raw listing and
  identity evidence are reused; per-release quality validation remains unchanged.
- Offline tests: canonical Python 757 plus distribution 7 passed; DSH Python 845
  passed; Node 123 passed. Each Python suite retained 3 skips, 1 live deselection
  and 15 subtests. Both skill validators and distribution synchronization passed.
- Network-blocked lifecycle simulation: 29/29, including completion-on-find before
  any download or watched sync. Playwright passed 1440/760/390px scope and action
  scenarios, four-width general UI checks, and theme/motion/isolation checks.
  All accounts, scheduler actions and retrieval results in these tests are fake;
  live Agent orchestration and clock-triggered runs have not been exercised.
- Local candidate only: no GitHub/npm/marketplace publication and no user tracking
  or Bangumi state migration. Codex retrieval behavior is unchanged by this change.

## Tracking inbox redesign: 2026-11-10

- The main row separates reviewed resources, actual download state and manual
  Bangumi sync. Expanded content has result, future-run and resource-requirement
  sections; collection metadata and run logs are secondary. Exceptions and new
  results precede quiet waiting. Completed downloads remain grouped by work.
- Resource requirements and schedule changes have separate, field-restricted
  host actions. Automatic-run OFF is independent of explicit run-once requests;
  those use a separate owned job without consuming or resuming a reservation.
- Download/retry reuses the selected hash and durable review evidence through
  the existing validator and idempotent delivery journal. It does not invoke an
  Agent or rediscover candidates. Changed requirements require revalidation.
  Accepted delivery is not download completion: qB evidence and actual files
  are still required. Found evidence no longer overwrites delivery statistics.
- Manual sync uses the latest validated find, including gaps and a confirmed
  finale, without requiring download completion. Failed hold/drop retries keep
  the original requested status; future tasks stay stopped. The execution
  context is restored on both success and failure so repeated calls cannot
  inherit another plan's identity.
- Offline regression: canonical Python plus distribution 764 passed; generated
  DSH Python plus policy 834 passed; each retained 3 skips, 1 live-test deselection
  and 15 passed subtests. Native Node: 119 passed. Both skill validators and
  distribution synchronization passed. The Windows sandbox's invalid temporary
  path required running isolated native tests outside that sandbox.
- Network-blocked cross-language lifecycle audit: 29/29. Additional download
  tests cover original-review reuse, failed submission recovery, stale policy,
  partial download, absent files and verified completion. Retrieval boundaries
  and native scheduler execution are fixtures, not a live Agent/clock test.
- Playwright/Edge passed inbox actions at 1440/760/390px, general UI at
  1360/800/390/320px and ocean theme/motion checks. All browser data are synthetic.
  No real Bangumi write, torrent submission or user schedule was performed.
- This is a local candidate only. Core retrieval policy is unchanged; GitHub,
  npm and the marketplace index are not published by this verification.

## Calendar scheduling and lifecycle audit: 2026-11-10

- Native schedule forms now support selected ISO weekdays, a daily wall clock,
  and a one-time date, all with an explicit IANA timezone. Existing elapsed-hour
  rules retain their original semantics. Native DSH owns clock/DST evaluation;
  the plugin does not convert future wall-clock dates using the workstation zone.
- Catch-up can be reserved for a future date without dispatching immediately.
  An ended reservation cannot be rearmed by condition edits or plan resume;
  choosing a new future time is required. Invalid creation leaves the form
  retryable. Changes preserve the owned schedule ID and separate pause state.
- Offline Node: 112 passed. Canonical Python plus distribution: 764 passed;
  generated DSH Python plus policy: 827 passed. Each Python run retained 3 skips,
  1 live-test deselection and 15 passed subtests.
- The network-blocked cross-language lifecycle audit passed 24/24, from adding
  a plan and reserving it through verified resource delivery, downloaded-file
  evidence and explicit Bangumi sync. Retrieval results and scheduler delivery
  were fixtures, not a live search or a real clock-triggered Agent execution.
- Playwright/Edge passed plan/calendar actions at 1440/760/390px, general UI at
  1360/800/390/320px, and ocean theme/motion checks. Weekly selections persist;
  one-time date/time controls fit narrow windows. Screenshot fixtures use only
  example data. No real account, download or schedule was changed by testing.
- Core retrieval policy is unchanged. This remains a local candidate; GitHub,
  npm and the marketplace index have not been published or updated.

## Native tracking workflow follow-up: 2026-11-10

- Expanded plans now lead with the validated find, verified downloaded episode
  ranges and next-check arrangement. Collection metadata and execution details
  are secondary disclosures. Catch-up results retain their own package link;
  they do not invent single-episode progress. Existing explicit sync and retained
  completed-history policy remain unchanged.
- Airing plans have a dedicated interval dialog. Queued/running, individually
  paused, missing and unavailable schedules are distinguished. Visible panels
  poll local status only, without invoking an Agent or rerunning release search.
  The general DSH scheduler remains the execution backend.
- Local plans load independently of Bangumi. Connection dialogs stay open with
  account and library-refresh feedback. Complete same-account caches survive
  transient refresh failures, but never mask invalid authorization or partial
  pagination. Serialized connection commits prevent an in-flight refresh from
  restoring a disconnected account. Corrupt optional caches are rebuildable.
- A full regression exposed a transient Windows access-denial race in legacy
  state reads during atomic replacement. Those specific OS errors now receive
  at most three short retries (170ms total delay); persistent errors still fail,
  and read-only calls create no files. A reader-lock approach was rejected by
  the existing no-side-effects test and is not shipped.
- Final offline Python: canonical core plus distribution 764 passed; generated
  DSH core and policy 827 passed. Each has 3 skips, 1 live-test deselection and
  15 passed subtests. Node: 102 passed with native test dependencies. The isolated
  cross-language plan lifecycle passed 18/18 with real network blocked.
- Playwright/Edge passed all three suites: plan actions (1440/760/390px), general
  UI (1360/800/390/320px), and ocean theme/motion lifecycle. Coverage includes
  slow-library/local-plan independence, interval saving, connection/disconnection,
  cleared credential fields, keyboard actions, dark mode and reduced motion.
- Both skill validators and payload synchronization passed. No real Bangumi
  write, torrent submission or live scheduled model execution was tested. This
  is a local candidate only; GitHub, npm and marketplace index are unchanged.

## Workflow and retry audit: 2026-11-10

- Optional `--compact` listing/detail views factor repeated fields into lossless
  tables; saved evidence and validation schemas are unchanged. Draft output is a
  receipt, not approval. The workflow reuses complete evidence and avoids a
  standalone audit immediately before delivery's own fresh audit. A synthetic
  75-row listing shrank from 32,212 to 5,695 serialized characters (82.3%). This
  is an output-size measurement, not a billed-token or live-agent benchmark.
- Panel execution reuses optional start-watching checks, including failures, for
  five minutes. Plan, binding or credential changes invalidate reuse. No-op
  snapshots no longer rewrite result files. No credentials enter reports.
- Duplicate queued/running checks are refused. Condition edits and plan resume
  preserve separate host/panel schedule pauses. Plan pause stops owned one-shot
  jobs as well as recurring ones. Scheduler outages persist the local stop and
  requested cloud status as pending before any cloud write is attempted.
- Changing episode/catch-up scope cannot reuse another scope's found history.
  Setup guidance recognizes saved Web API settings and does not require a remote
  download directory to exist on the local computer.
- Offline Python: core plus distribution 758 passed; DSH 821 passed. Each retained
  3 skips, 1 live-test deselection and 15 passed subtests. Native Node tests and
  the independent scheduler harness exercise fake integrations only. The latter
  passed all 70 checks after reproducing and fixing two additional pause bugs.
  The cross-language lifecycle simulation passed 18/18 with real network blocked.
- Playwright/Edge plan-action checks passed at 1440, 760 and 390px, including
  dark mode, disabled sync, hold, retained completed history, catch-up, cover
  fallback and edit errors. Both skill validators and distribution checks passed.
- No real Bangumi write, torrent submission or live scheduled model run was used.
  This remains an unpublished local candidate; npm/index are not changed.

## Local UI follow-up: four-part seated whale

2026-11-09: the panel now uses four bundled 512px transparent action clips:
idle -> receive -> reading -> return -> the same idle. Display remains fixed at
150px desktop and 132px narrow. Idle and reading master hashes are unchanged.
Only a tiny residual receive-cuff glint was cleaned after the reviewed transition.
The older CSS-clipped body/leg motion is no longer layered over the new artwork.

- A single canvas player uses the source clip timings. Requests wait for safe
  clip boundaries; hidden/offscreen panels, disabled motion and reduced-motion
  preferences freeze the current position. Missing ImageDecoder uses a static
  same-character poster. Mascot interactions call no host or network service.
- Browser/Edge: three full real-time cycles at each size; light/dark, seating,
  nonblank transparent canvas, stable rows, keyboard/click, no dragging, pause/
  resume, visibility lifecycle and unsupported-decoder fallback passed.
- General panel browser checks passed: tabs, search, filters, sorting, details,
  configuration dialogs, empty/error states and four viewport widths.
- Ocean lifecycle/layout checks also passed. Node: 79 passed, 5 skipped because
  optional real-host integration dependencies were not configured. The actual
  npm tarball was packed locally and verified: 262 runtime files and 364 source
  inputs, with exact file comparisons and Python compilation. It was NOT uploaded.
- Core plus distribution Python: 749 passed, 3 skipped, 1 deselected and 15
  subtests. DSH Python: 807 passed, 3 skipped, 1 deselected and 15 subtests.
  Each suite has an existing unregistered `live` marker warning; live tests
  were excluded. Shared payload synchronization reports no drift.
- This is a local-only UI update, not a new release. Public npm, GitHub,
  marketplace index, host adapters, user state and schedules remain unchanged.

The older "no whale" note below describes its historical presentation pass,
not the current local candidate. The active local desktop profile received only
the visual client/license and seven mascot asset/provenance files. Old files
were backed up first; all nine destination hashes match the tested files. Host
code and profile configuration hashes stayed unchanged. The real DSH panel was
then opened and visibly showed the new idle and reading poses. This does not
constitute a live search, scheduler execution, cloud write or download test.

## Latest: explicit progress and retained download history

2026-11-08: supersedes the older panel-policy notes below. Executing a native
plan marks a bound non-watched collection as watching. Progress/finale writes
are explicit native button actions, based on the latest validated find rather
than delivery, download completion, broadcast latest or the next target. Finale
sync can mark watched before the download ends. Existing watched collections
never regress. The dropdown contains only on-hold and dropped.

Completed is grouped download-task history: audited hashes, qB completion evidence
and actual files/sizes in the configured directory must agree. Preallocation alone
does not qualify. History survives cloud status changes and later checks; only
explicit deletion hides a plan. Old delivery outbox writes and automatic cleanup
are blocked for panel-owned tracks. Owned legacy scheduler prompts are upgraded
without resuming paused schedules. Codex/non-panel behavior is unchanged.

- Core Python: 742 passed, 3 skipped, 1 deselected, 15 subtests; distribution: 7 passed.
- DSH Python including adapters/panel policy: 807 passed, 3 skipped,
  1 deselected, 15 subtests.
- Node: 70 passed with native DSH/Cordis integration dependencies. Includes
  pause-before-cloud, failure retention, finale partial-success retry, gap filling,
  collection field preservation, old prompt migration and no-result rejection.
- All three Playwright/Edge checks passed: general UI, underwater themes/motion,
  and plan actions. Desktop, narrow/mobile, keyboard, disabled primary with usable
  dropdown, compact disclosures, catch-up mode and cover fallback are covered.
- Both skill validators, Python compilation and reproducible distribution sync passed.
- Tests use fake accounts and isolated files. No real Bangumi write, torrent add or
  live scheduled Agent execution was performed. Host reload is required after local
  installation; the public npm release/market index remain unchanged at 0.2.2.

### Follow-up: lifecycle audit corrections

- Work/season/track/Bangumi identity replacement on an existing plan is refused
  before file or schedule changes. New plans preserve the old work's history;
  ordinary condition edits retain the existing identity and progress. A previously
  missing Bangumi binding can only be filled from that plan's verified evidence.
- Later verified collection writes supersede stale failed start-status attempts
  in the read projection; raw attempt evidence is not erased. Newer failures,
  missing timestamps, and incomplete progress remain explicit.
- Editing conditions uses the saved title/season, not enriched display metadata.
  Save errors are visible inside the plan form, including narrow/dark layouts.
- The offline cross-language lifecycle audit passed all 18 checks, with real
  network disabled and synthetic account/download files only. Node: 78 passed.
  Core plus distribution: 749 passed; DSH Python: 807 passed. Each Python suite
  retained 3 skips, 1 deselection and 15 passed subtests. All three UI checks,
  compilation, both skill validators and reproducible sync passed again.
- No personal Bangumi collection was read or written. No real download or live
  scheduled Agent run was used. This remains a local unpublished candidate.

Earlier verification notes below describe preceding local passes and the last
published build, not the current manual-sync semantics.

2026-11-08: rebuilt the DSH panel around separate DSH-plan and Bangumi-library tabs,
with local search/filter/sort, inline details and host-owned Bangumi/qBittorrent
configuration dialogs. Existing search and quality rules are unchanged.
The `/api` collision fix is also included; the plugin uses `/anime-release` RPC.

- Core plus distribution checks: 749 passed, 3 skipped, 1 deselected, 15 subtests passed.
- DSH adapter plus shared tests: 789 passed, 3 skipped, 1 deselected, 15 subtests passed.
- Fixed quick-start examples and the shared Chinese tutorial are included; explicit
  `--guide` works even after setup without modifying state or opening a window.
- Node: 31 passed with the current DSH connection dependency set, including host configuration redaction, native plans and real Connection RPC ownership in both load orders. Without those dependencies, four integration tests are skipped.
- Windows: both small empty forms visibly inspected; prior full-form prototype's
  skip flow was tested but is no longer part of the UI. Credential failure/success,
  host isolation and saved desktop paths are covered by offline tests. No real
  token was entered, collection changed, or download submitted for this check.
- Both skill validators and shared-payload reproducibility checks passed. Playwright UI checks passed for the two tabs, local search, filters, sorting, details, configuration dialogs, empty/error states and four viewports.

Tests used isolated normal-user temporary directories because sandbox-created
pytest temp directories had incompatible permissions. One first normal-user run
hit Windows access denial replacing a concurrently read state file; its focused
retry and a subsequent complete run both passed. No production locking or tests
were weakened. This is not an npm publication claim; the public release and index
remain at 0.2.2.

The native scheduler adapter follows the Host `status: active/paused/ended`
contract (not a fabricated boolean readback). Tests cover pending one-shot
deduplication, optimistic revisions, ownership guards and paused-plan behavior.
Dispatch is explicitly labelled queued, not execution/download success. Shared
core qBittorrent settings now apply to Web API credentials and download directory;
explicit request paths and environment credentials take precedence.

These checks do not exercise an actual scheduled Agent run, real credentials,
cloud writes or a download in a logged-in DSH desktop. End-to-end finale cleanup
of panel-created plans still needs that integration validation before release.

## Underwater presentation pass (local preview only)

2026-11-08: DSH-only visual changes add independently generated light/dark
painted-seabed assets, a small transparent carved-starfish accent, and an original
double-antenna TV icon. No underwater city, whale mascot or pet interface is
included. The assets are embedded in the native Client bundle; no RPC route,
tracking migration, core search rule or Codex onboarding change was needed.

- The desktop list uses aligned columns; narrow layouts use labelled stacked
  cells. Missing progress and unverified schedule/sync states remain explicit.
- Up to six decorative bubbles (three on narrow screens), persisted motion
  preference, system reduced motion, document visibility and intersection
  pausing were exercised. Decoration does not intercept input or alter layout.
- Playwright/Edge passed both `check_ui.mjs` and `check_ocean_ui.mjs`: tabs,
  filtering/sorting, inline details, forms, errors/empty states, keyboard access,
  native DSH dark-theme attribute, embedded-image loading, host style isolation,
  long titles, and 1440/1360/1024/800/390/320px layouts. Screenshots are in the
  ignored `.preview/` folder and use labelled fixtures, not personal data.
- Node: 34 passed with the real DSH integration dependencies. Python: 742 core
  tests plus 7 distribution tests passed; 789 DSH tests passed. Each complete
  suite reports 3 skipped, 1 deselected and 15 subtests passed. DSH retains the
  existing unknown `live` marker warning.
- The first sandbox Python run failed two normal-user-context broker checks.
  A retry initially had a missing temporary parent directory; after correcting
  that test invocation, both complete isolated normal-user runs passed. No test
  assertion or production permission guard was changed.

This is not a logged-in DSH desktop or live download test. The installed plugin,
GitHub, npm and marketplace index are intentionally not updated by this pass.

### Separate current ribbon

The follow-up adds a code-native foreground ribbon (`CurrentRibbon.jsx`), not a
replacement ocean bitmap. Light and native dark themes use separate translucent
edge/fill tokens. Its right-hand widened, slightly depressed surface leaves space
for a future 64px seated character and 32px dangling feet without covering header
controls or metrics. No character or pet behavior is mounted. Decoration remains
noninteractive and excluded from accessibility output. Existing responsive and
theme checks cover the ribbon; the preview includes separate day/night crops.
The local candidate is synchronized to the desktop plugin on explicit user
request, with a code backup and unchanged profile dependencies/personal data;
GitHub/npm publication remains deferred.

The header follow-up consolidates tools into a single non-wrapping refresh /
settings / help row. A settings dialog holds Bangumi and qBittorrent status and
configuration entries plus the persisted background-motion switch. Long unknown
status labels no longer reflow the header. Both Playwright suites and all 34 Node
tests passed after this change; keyboard, settings navigation, native dark theme
and single-row tools at narrow widths are covered.

### Desktop worker connection repair

The previous HTTP-only `/anime-release` route was not available to DSH's
worker-local shared Fetch carrier, and its optional webServer injection did not
run in that mode. Client requests now use owner-only exact routes below
`/api/anime-release/`, without replacing the Gateway's `/api` interceptor. The
legacy HTTP route remains for compatibility. Registration no longer requires
webServer for the new carrier. A real Connection test without webServer covers
config reads, a simulated token connection/disconnection, malformed requests and
disposal. Both Gateway load orders and non-owner rejection are tested. All 35 Node
tests and both UI suites pass. Configuration failures are visible inside their
dialogs with safe, specific messages; transport errors do not disclose payloads.
No real Token is used by these tests. An installed desktop restart and personal
account retry are still required to confirm the user's live connection.

### Bangumi outbound proxy repair

The installed-machine unauthenticated probe reproduced ECONNRESET on the former
direct Node fetch path. The same public API returned the expected HTTP 401
without credentials through the already-enabled Windows system proxy. Bangumi
verification and library reads now share an isolated `node:https.Agent` using
Node 24.5+ `proxyEnv`, with environment precedence and Windows static proxy
fallback. No global Agent, dispatcher, TLS validation or qBittorrent networking
is changed. The repaired module's automatic system-proxy path was live-probed
without a Token and returned 401. Timeout/DNS/TLS/reset/refused/unsupported-proxy
failures use distinct safe codes. Unit tests use fake transports, not credentials;
all 38 Node tests and both UI suites pass. Personal account validation is not
claimed. PAC-only proxies are not automatically interpreted by this adapter.

## Previous published build: 0.2.2

Build date: 2026-11-08. Host: Windows, Node.js 24.16.0, Python 3.14.0.
Reference DSH: 0.2.2-rc.1, source commit
`fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159`.

Release artifacts use tag `dsh-v0.2.2`. The project-maintained marketplace index
uses the exact npm version after registry publication is verified. The same
checked tarball is used for npm and GitHub. This is not a claim of public
community-market acceptance or a logged-in DSH desktop test.

This release changes publication metadata, index generation and installation
documentation, not the shared search core or DSH runtime. The offline suites
were rerun for 0.2.2; the independent UI screenshots below were captured for 0.2.1
and its unchanged runtime, not repeated as a new desktop integration test.

## Completed checks

- Shared core and generated DSH payload include the same optional Bangumi mirror.
  The Codex suite plus synchronization tests passed **738 tests**, with 15 subtests passed,
  3 skipped and 1 deselected. Rebuilding the DSH payload produces no diff.
- Python adapter and upstream offline suite: **778 passed**, 15 subtests passed,
  3 skipped, 1 deselected. Skips cover opt-in network/process tests and a
  Windows broker stderr-stream condition. No real client submission occurred.
- JavaScript: **14 passed**, including actual Cordis 4.1.0 / DSH SkillRegistry
  registration, skill loading and disposal, the official market-index parser,
  and checks that both localized detail pages and their screenshots are packaged.
  New checks cover owner-only read-only RPC, cancellation, state projection,
  byte limits, native ModuleLoader registration, style disposal and unsent draft
  handoff. Real Cordis verifies optional Connection registration and disposal.
  The official market parser accepts both pinned Git and exact npm sources;
  npm targets retain the package name and public registry. Invalid/mixed source
  identifiers are refused. Package and lockfile versions are checked together.
- Bangumi fixtures cover credential redaction, pagination, bounded personal ratings/
  comments, cache hits, exact episode mapping, explicit watched scopes, duplicate
  write recovery, failed downloads and cloud outages. Reads/collection changes do
  not change local targets or validation; cloud failures do not block delivery.
  Untracked library reads/writes create no local anime tracking entries.
- Playwright + installed Edge: desktop 1360px, tablet 800px, mobile 390px and
  narrow 320px; light/dark screenshots inspected. Filter, record details, pending
  operation guard, search scope, Chinese requirement, download consent, empty
  state and error/retry passed. The Bangumi fixture shows cloud watch count separately
  from local delivered/next episodes, including a cloud on-hold status. The harness uses the exact shipped Panel component
  with labeled example data, not a logged-in DSH session.
- `quick_validate.py`: skill valid.
- Runtime contains the prebuilt Client factory, Host endpoint and all Skill scripts.
  Development dependencies and preview fixtures are not runtime dependencies.
- The weekly adapter accepts DSH's `HH:mm:ss.SSS` output without rounding a
  nonzero second. Remote qBittorrent paths survive Windows parsing unchanged.
- Missing, malformed, partial and stale scheduler readbacks block cleanup.
- Release packaging excludes tests, bytecode, temporary files and personal state.
  `UPSTREAM.json` records the source snapshot and the explicitly adapted files.
- All **235** packed runtime files matched the build tree; the source archive contains
  **307** files. All packed Python source files
  compiled in memory without generating bytecode in the installation directory.

The Node sandbox run could not create its redirected temporary directory.
The approved normal-user rerun passed all 14 tests. Both complete Python suites
passed using isolated temporary directories in the normal-user context. No
assertions were skipped or weakened to fix the environment.
Both suites retain one pre-existing unknown `live` marker warning.

## Scope

Tests use fake clients and scheduler fixtures. They do not prove the behavior of a
logged-in desktop session, its model, its tool permissions, a live schedule or a
real download. GitHub publication and a valid custom index do not imply inclusion
in a public community market or publication to npm.
Bangumi authorization and read-only completed-list access were verified in the
installed Codex distribution using the owner's authorized account. No token,
account identifier or collection content is included in the release. Real cloud
writes and DSH-side live authorization were not exercised.
macOS/Linux path selection is unit-tested; their desktop clients are not tested
on those operating systems. See [COMPATIBILITY.md](COMPATIBILITY.md).

## Reproduce current candidate checks

The source ZIP contains the tests. For native component tests, set
`DSH_TEST_NODE_MODULES` to a separate dependency directory containing
`@deepseek-ai/cordis@4.1.0`, `@deepseek-ai/dsh-skill@0.2.2-rc.1`,
`@deepseek-ai/dsh-client-connection@0.2.2-rc.1`,
`@deepseek-ai/dsh-plugin-market-index@0.2.2-rc.1`, `yaml@2.8.1` and `semver@7.7.3`.
These are test-only dependencies, not plugin installation requirements.
Without this variable, native-component tests report skipped, not passed.

```sh
npm ci --ignore-scripts
npm run build
npm test
python -m pytest tests/test_dsh_adapter.py tests/test_panel_policy.py skills/find-nyaa-anime-release/tests --rootdir . -m "not live" -p no:cacheprovider
npm pack --ignore-scripts
python tools/verify_and_archive.py --tarball dsh-find-nyaa-anime-release-0.2.5.tgz --output-dir dist
```

The archive verifier compares each packed runtime file against the build tree,
checks the complete allowlist, and emits a source ZIP plus SHA256 checksums.

For visual tests, run `npm run preview`, then `node tools/check_ui.mjs`. Provide
Playwright through `PLAYWRIGHT_NODE_MODULES` (or a locally installed package).
`PLAYWRIGHT_CHANNEL=msedge` uses an installed Edge; omit it for Playwright Chromium.
Screenshots stay under ignored `.preview/`. Only the explicitly labeled example
desktop screenshot is included in the documentation.
