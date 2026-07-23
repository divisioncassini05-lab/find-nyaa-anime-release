# Airing Watch State

Use this reference for vague repeat requests, state repair, latest/next behavior, or completion cleanup.

State file:

By default the state lives at `~/Downloads/Anime_Tracking/airing_watch_state.json`.
Set `ANIME_TRACKING_STATE` to use another location. Existing installations using
the earlier Windows path continue to reuse it automatically.

Useful commands:

```bash
python scripts/find_anime_release.py "TITLE" --tier browse --include-magnet --legal-ok --json
python scripts/find_anime_release.py "TITLE" --latest --tier browse --json
python scripts/find_anime_release.py "TITLE" --official-air-date --episode 4 --no-state-update --json
python scripts/airing_watch_state.py probe "TITLE"
python scripts/airing_watch_state.py get "TITLE"
python scripts/airing_watch_state.py delete "TITLE"
```

## Rules

- Only a current/still-airing TV, TV_SHORT, or ONA may enter state. Old shows, movies, completed shows, OVAs, and specials stay stateless.
- Resolve the exact work before consulting progress. Match records by `bangumi_id` or `anilist_id` when available, then by title aliases for backward compatibility.
- `search_titles` is an ordered list of English/romaji Nyaa query names. `verified_search_titles` contains names that actually produced a selected release. A Chinese-only tracked record is incomplete and must be enriched through Bangumi before Nyaa is queried.
- New aliases and stable IDs are learned only when they bridge to an already tracked airing show or when a newly resolved airing show is added. Do not treat short technical cache entries as aliases or watch history.
- A tracked title-only request targets `next_episode`. An explicit season or episode wins.
- Run `probe` before an ordinary title search. It is read-only and returns compact progress plus verified Nyaa search titles; a miss does not create state.
- Persist `mainline_scope` and `related_titles` for current shows when AniList supplies them. A sole mainline season may inherit missing release season labels; side stories and multi-season ambiguity may not.
- When the user changes or selects only the season of a tracked show, preserve `next_episode`. Normalize the season to `SNN` and search that exact next episode; do not ask the user to repeat an episode number.
- `--latest` first asks AniList schedule metadata for the latest regular episode. When a future `nextAiringEpisode` exists, the latest aired regular episode is `nextAiringEpisode - 1`.
- `--official-air-date --episode N` is a read-only failure-recovery query. It never updates tracking state and permits a Nyaa listing scan only for a currently releasing mainline anime whose official series start date is no more than 366 days old. Recent episodes scan from air date to today; older episodes scan only from the exact air date through seven days later. Finished new anime and long-running old anime are ineligible.
- Do not infer a rescue start date from Nyaa upload timestamps when AniList has no exact `AiringSchedule` entry.
- If the target has not aired, return `not_aired_yet`; do not return the previous episode. If it aired but Nyaa has no qualified release, return the matching structured status and leave `next_episode` unchanged.
- A successful integer regular episode updates `latest_known_episode` and `next_episode = episode + 1`. It does not mark the episode watched.
- Specials, decimal episodes, unknown candidates, and `needs_confirmation` never advance state.
- Remove a record only when AniList reliably confirms the final regular episode or the user explicitly says the show is finished.
