# Maintaining both distributions

The user's update request applies to **both** the Codex skill and the DSH plugin.
Keep the existing repository and Codex installation URL stable.
The public project name is `dsh-find-anime` (动漫搜索与追番管理); keep
technical identifiers and installation URLs unchanged.

- Canonical public core: `skills/find-nyaa-anime-release/`.
- DSH distribution: `plugins/dsh-find-nyaa-anime-release/`.
- DSH host differences belong in `overlays/` and `tools/sync_skill.py` inside the
  plugin, not in its generated `skills/` directory. Never copy Codex-only paths,
  task IDs or automation APIs over those adapters.
- When importing from a personal installation, review the diff and keep personal
  scheduler destinations, state, credentials and caches out of the public core.
  In particular, preserve the generic public scheduler destination paragraph.
- After changing the public core, run `python tools/sync_skills.py --bump patch`
  and `python tools/sync_skills.py --check`. On the first unpublished release,
  omit the version bump. Changed builder contracts must be reviewed, not bypassed.
- If a source workflow changes, review the corresponding DSH overlay for semantic
  parity as well; matching hashes alone cannot prove host behavior is equivalent.
- Run both Python suites in separate processes and the DSH Node tests. Build and
  verify the actual npm tarball. Keep host/GUI/live-download test limits explicit.
- Before a new DSH release, update its version (also for wrapper-only changes),
  README version examples and build report. Commit both distributions together.
- Release requests include npm publication as well as GitHub. Publish the same
  verified tarball to the public `dsh-find-nyaa-anime-release` npm package with
  the `latest` tag. Use existing npm authorization; never put tokens in this repo.
  Verify the registry version, `latest` tag and tarball integrity before declaring
  publication complete. A local pack or GitHub push is not an npm release.
  A `0.0.0-stage` placeholder is not a released version. If staged, use npm 11.15+
  `stage list/view/approve` and let the owner complete browser 2FA; then repeat
  the public metadata/integrity checks. Do not reinstall the staging placeholder.
- After the code commit and verified npm publication, generate `marketplace.json`
  with `--source npm --path plugins/dsh-find-nyaa-anime-release`, then commit the
  index. Keep the index URL stable. Do not advertise an unpublished npm version.
  The generator's Git mode is only an explicit alternative, not the default
  release channel: path/Git/tarball installations lack native registry updates.
- For an authorized GitHub update, push both commits and attach the matching tgz,
  source ZIP and checksums to `dsh-v<VERSION>`. Never replace another release's
  assets or force-push. Market indexing is not proof of community-market approval.
- Existing DSH profiles should use the registry package under its original name.
  Preserve profile selection, external data and schedules on migration. Verify
  the installed source and version; the latest installed version should not show
  an update badge until a newer compatible npm version is published.

User tracking state stays on each user's machine. Synchronization here concerns
code, rules and distribution artifacts, not personal tracking/download history.
