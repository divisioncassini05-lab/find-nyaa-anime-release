# Build verification: 0.2.2 npm distribution

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

## Reproduce

The source ZIP contains the tests. For native component tests, set
`DSH_TEST_NODE_MODULES` to a separate dependency directory containing
`@deepseek-ai/cordis@4.1.0`, `@deepseek-ai/dsh-skill@0.2.2-rc.1`,
`@deepseek-ai/dsh-plugin-market-index@0.2.2-rc.1`, `yaml@2.8.1` and `semver@7.7.3`.
These are test-only dependencies, not plugin installation requirements.
Without this variable, the three native-component tests report skipped, not passed.

```sh
npm ci --ignore-scripts
npm run build
npm test
python -m pytest tests/test_dsh_adapter.py skills/find-nyaa-anime-release/tests -m "not live" -p no:cacheprovider
npm pack --ignore-scripts
python tools/verify_and_archive.py --tarball dsh-find-nyaa-anime-release-0.2.2.tgz --output-dir dist
```

The archive verifier compares each packed runtime file against the build tree,
checks the complete allowlist, and emits a source ZIP plus SHA256 checksums.

For visual tests, run `npm run preview`, then `node tools/check_ui.mjs`. Provide
Playwright through `PLAYWRIGHT_NODE_MODULES` (or a locally installed package).
`PLAYWRIGHT_CHANNEL=msedge` uses an installed Edge; omit it for Playwright Chromium.
Screenshots stay under ignored `.preview/`. Only the explicitly labeled example
desktop screenshot is included in the documentation.
