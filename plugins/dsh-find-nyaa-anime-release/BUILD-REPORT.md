# Build verification: 0.1.0

Build date: 2026-11-07. Host: Windows, Node.js 24.16.0, Python 3.14.0.
Reference DSH: 0.2.2-rc.1, source commit
`fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159`.

## Completed checks

- Both distributions were rebuilt from the shared public core. The Codex suite
  plus synchronization tests passed **704 tests**, with 15 subtests passed,
  3 skipped and 1 deselected. Rebuilding the DSH payload produces no diff.
- Python adapter and upstream offline suite: **744 passed**, 15 subtests passed,
  3 skipped, 1 deselected. Skips cover opt-in network/process tests and a
  Windows broker stderr-stream condition. No real client submission occurred.
- JavaScript: **4 passed**, including actual Cordis 4.1.0 / DSH SkillRegistry
  registration, skill loading and disposal, the official market-index parser,
  and checks that both localized detail pages and their screenshots are packaged.
- `quick_validate.py`: skill valid.
- The actual `.tgz` installed successfully into an isolated path with spaces.
  The installed plugin loaded/disposed through the official registry; its Python
  doctor returned `ready` and a foreign-working-directory `watch inspect` returned
  `not_tracked` without creating user state. This was not a desktop UI installation.
- The weekly adapter accepts DSH's `HH:mm:ss.SSS` output without rounding a
  nonzero second. Remote qBittorrent paths survive Windows parsing unchanged.
- Missing, malformed, partial and stale scheduler readbacks block cleanup.
- Release packaging excludes tests, bytecode, temporary files and personal state.
  `UPSTREAM.json` records the source snapshot and the explicitly adapted files.
- Every packed runtime file matched the build tree; all packed Python source files
  compiled in memory without generating bytecode in the installation directory.

## Scope

Tests use fake clients and scheduler fixtures. They do not prove the behavior of a
logged-in desktop session, its model, its tool permissions, a live schedule or a
real download. GitHub publication and a valid custom index do not imply inclusion
in a public community market or publication to npm.
macOS/Linux path selection is unit-tested; their desktop clients are not tested
on those operating systems. See [COMPATIBILITY.md](COMPATIBILITY.md).

## Reproduce

The source ZIP contains the tests. For native component tests, set
`DSH_TEST_NODE_MODULES` to a separate dependency directory containing
`@deepseek-ai/cordis@4.1.0`, `@deepseek-ai/dsh-skill@0.2.2-rc.1`,
`@deepseek-ai/dsh-plugin-market-index@0.2.2-rc.1`, `yaml@2.8.1` and `semver@7.7.3`.
These are test-only dependencies, not plugin installation requirements.
Without this variable, the two native-component tests report skipped, not passed.

```sh
npm test
python -m pytest tests/test_dsh_adapter.py skills/find-nyaa-anime-release/tests -m "not live" -p no:cacheprovider
npm pack --ignore-scripts
python tools/verify_and_archive.py --tarball dsh-find-nyaa-anime-release-0.1.0.tgz --output-dir dist
```

The archive verifier compares each packed runtime file against the build tree,
checks the complete allowlist, and emits a source ZIP plus SHA256 checksums.
