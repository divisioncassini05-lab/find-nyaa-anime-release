# Maintaining both distributions

The user's update request applies to **both** the Codex skill and the DSH plugin.
Keep the existing repository and Codex installation URL stable.
The Chinese display name is `动漫搜索与自动追番`; keep technical identifiers unchanged.

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
- After that code commit, generate `marketplace.json` using its real commit and
  `--path plugins/dsh-find-nyaa-anime-release`, then commit the index. Never point
  an index at an older commit that lacks the declared plugin version.
- For an authorized GitHub update, push both commits and attach the matching tgz,
  source ZIP and checksums to `dsh-v<VERSION>`. Never replace another release's
  assets or force-push. Market indexing is not proof of community-market approval.

User tracking state stays on each user's machine. Synchronization here concerns
code, rules and distribution artifacts, not personal tracking/download history.
