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
python scripts/airing_watch_state.py record-found "TITLE" --episode 4
python scripts/airing_watch_state.py delete "TITLE"
```

## Rules

- Only a current/still-airing TV, TV_SHORT, or ONA may enter state. Old shows, movies, completed shows, OVAs, and specials stay stateless.
- Resolve the exact work before consulting progress. Match records by `bangumi_id` or `anilist_id` when available, then by title aliases for backward compatibility.
- `search_titles` is an ordered list of English/romaji Nyaa query names. `verified_search_titles` contains names that actually produced a selected release. For a tracked search, use the verified titles as the ordinary Nyaa query lane and omit the broad Chinese display title from that lane; the display title is only a strict-Chinese supplemental query when subtitles are required. A Chinese-only tracked record is incomplete and must be enriched through Bangumi before Nyaa is queried.
- New aliases and stable IDs are learned only when they bridge to an already tracked airing show or when a newly resolved airing show is added. Do not treat short technical cache entries as aliases or watch history.
- A tracked title-only request targets `next_episode`. An explicit season or episode wins.
- The tracked record supplies the work identity and target: do not rediscover the work from a broad display-name query or accept a same-number release from a similarly named different work.
- An explicit older or same-episode request is retrieval-only. Return the qualified release but leave the state file byte-for-byte unchanged.
- Run `probe` before an ordinary title search. It is read-only and returns `watched_episode`, compact progress, and verified Nyaa search titles; a miss does not create state.
- After a probe miss, ordinary Nyaa discovery remains read-only. Before returning the first result, route the exact work and episode through `find_anime_release.py` without `--no-state-update`. If metadata confirms a current/still-airing TV, TV_SHORT, or ONA, create the record automatically. A successful episode becomes watched and advances `next_episode`; a qualified current show whose target is unavailable or unqualified may enter `waiting` without advancing watched progress.
- Treat `watched_episode` as the user's actual completed progress. For this user, successfully returning a fully qualified regular episode with its magnet means the episode has been watched.
- Persist `mainline_scope` and `related_titles` for current shows when AniList supplies them. A sole mainline season may inherit missing release season labels; side stories and multi-season ambiguity may not.
- When the user changes or selects only the season of a tracked show, preserve `next_episode`. Normalize the season to `SNN` and search that exact next episode; do not ask the user to repeat an episode number.
- `--latest` first asks AniList schedule metadata for the latest regular episode. When a future `nextAiringEpisode` exists, the latest aired regular episode is `nextAiringEpisode - 1`.
- `--official-air-date --episode N` is a read-only failure-recovery query. It never updates tracking state and permits a Nyaa listing scan only for a currently releasing mainline anime whose official series start date is no more than 366 days old. Recent episodes scan from air date to today; older episodes scan only from the exact air date through seven days later. Finished new anime and long-running old anime are ineligible.
- Do not infer a rescue start date from Nyaa upload timestamps when AniList has no exact `AiringSchedule` entry.
- If the target has not aired, return `not_aired_yet`; do not return the previous episode. If it aired but Nyaa has no qualified release, return the matching structured status and leave `next_episode` unchanged.
- After a direct Nyaa verification succeeds for a tracked integer regular episode strictly ahead of completed progress, run `record-found`. It updates `watched_episode`, `latest_known_episode`, and `next_episode = watched_episode + 1`.
- `record-found` returns `unchanged` and performs no file write when the requested episode is equal to or older than completed progress. Derive legacy completed progress from `watched_episode`, or from `next_episode - 1` when `watched_episode` is absent.
- A latest-available request follows the same rule: return the latest qualified release, but advance only when its episode is strictly ahead of completed progress.
- The high-level resolver must apply the same forward-only, zero-write rule on a qualified regular-episode success.
- Never update watched progress for discovery-only rows, failures, unqualified results, missing magnets, specials, decimal episodes, movies, or whole-season packages. Do not use low-level `record-found` to create an untracked title; use the high-level resolver so current-airing eligibility and stable identity are verified first.
- Specials, decimal episodes, unknown candidates, and `needs_confirmation` never advance state.
- Remove a record only when AniList reliably confirms the final regular episode or the user explicitly says the show is finished.
