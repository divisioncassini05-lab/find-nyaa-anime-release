# Execute a DSH panel search

`[anime-plan:ID]` supplies the plan ID. Run from the absolute skill resource
directory. Every command uses `dsh_panel_run.py --plan-id ID search`; for automatic
runs add `--scheduled` before `search`. The wrapper supplies track, intent and exact
saved quality policy, checks the live plan on each stage, and records validated
finds. Do not call the core script directly for a panel task. Do not add policy
flags to override the saved plan.

<!-- SHARED_SEARCH_FLOW -->

For `missing_episodes`, first establish latest regular episode N, then use the
wrapper's `targets --through N`. Search only returned gaps with `--episode N`;
preserve partial finds. Package scopes retain the plan title/season/Bangumi ID
from the returned context while independently verifying work kind and count.

Finish honors the saved download switch. Do not call watched/flush/finalize,
delete schedules or edit result files; the panel owns manual progress sync.
Optional start-watching failure does not restart retrieval. On a permission
boundary use the host's authorization flow or report the stage; no custom retry
scripts, ACL edits or implementation-source investigation for normal operation.
