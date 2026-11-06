"""Extracted policy module: metadata."""

from __future__ import annotations
from .settings import CURRENT_NEW_ANIME_MAX_AGE_DAYS, MAINLINE_FORMATS, SCHEDULE_CACHE_SECONDS, SCHEDULE_CACHE_VERSION

import copy
import json
import time
import urllib.error
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from release_identity import normalize_season_number


import completion as completion_policy


def schedule_cache_key(resolved: ResolvedAnime) -> str:
    from .legacy_models import ResolvedAnime
    from .queries import norm
    if resolved.anilist_id:
        return f"id:{resolved.anilist_id}"
    return f"title:{norm(resolved.title)}"


def load_schedule_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": SCHEDULE_CACHE_VERSION, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": SCHEDULE_CACHE_VERSION, "entries": {}}
    if (
        not isinstance(data, dict)
        or data.get("version") != SCHEDULE_CACHE_VERSION
        or not isinstance(data.get("entries"), dict)
    ):
        return {"version": SCHEDULE_CACHE_VERSION, "entries": {}}
    return data


def save_schedule_cache(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temp.replace(path)
    except OSError:
        return


def resolved_snapshot(resolved: ResolvedAnime) -> dict[str, Any]:
    from .legacy_models import ResolvedAnime
    return {
        "title": resolved.title,
        "aliases": resolved.aliases,
        "search_titles": resolved.search_titles,
        "verified_search_titles": resolved.verified_search_titles,
        "season": resolved.season,
        "current": resolved.current,
        "trackable": resolved.trackable,
        "source": resolved.source,
        "format": resolved.format,
        "status": resolved.status,
        "episodes": resolved.episodes,
        "duration_min": resolved.duration_min,
        "bangumi_id": resolved.bangumi_id,
        "anilist_id": resolved.anilist_id,
        "next_airing_episode": resolved.next_airing_episode,
        "next_airing_at": resolved.next_airing_at,
        "mainline_scope": resolved.mainline_scope,
        "related_titles": resolved.related_titles,
        "continuation_parts": resolved.continuation_parts,
        "completion": resolved.completion,
        "metadata_titles": resolved.metadata_titles,
        "identity_conflicts": resolved.identity_conflicts,
    }


def resolved_from_snapshot(snapshot: dict[str, Any], fallback: ResolvedAnime) -> ResolvedAnime:
    # Do not fill missing identity evidence with the caller's requested season.
    from .legacy_models import ResolvedAnime
    return merge_resolved(fallback, ResolvedAnime(**snapshot))


def read_schedule_snapshot(path: Path, key: str) -> dict[str, Any] | None:
    return None  # v1-v6 merged authority snapshots are deliberately retired.


def write_schedule_snapshot(path: Path, key: str, resolved: ResolvedAnime) -> None:
    # Legacy callers may cache raw evidence, never their merged state projection.
    if resolved.work_identity is not None:
        from . import evidence_cache
        from .evidence import validate
        for evidence in resolved.evidence:
            evidence_cache.write(path, resolved.work_identity, validate(resolved.work_identity, evidence))


def write_schedule_snapshots(path: Path, keys: list[str], resolved: ResolvedAnime) -> None:
    from .legacy_models import ResolvedAnime
    for key in dict.fromkeys(keys):
        write_schedule_snapshot(path, key, resolved)


def official_air_date_cache_key(media_id: int, episode: int, identity=None) -> str:
    if identity is not None:
        from .evidence_cache import key
        return f'airing:{key(identity, "anilist", media_id)}:{episode}'
    return f"airing:external:{media_id}:{episode}"


def read_official_air_date_cache(
    path: Path, media_id: int, episode: int, identity=None
) -> dict[str, Any] | None:
    cache = load_schedule_cache(path)
    entry = cache["entries"].get(official_air_date_cache_key(media_id, episode, identity))
    if not isinstance(entry, dict):
        return None
    try:
        if float(entry.get("expires_at", 0)) <= time.time():
            return None
    except (TypeError, ValueError):
        return None
    payload = entry.get("official_air_date")
    return payload if isinstance(payload, dict) else None


def write_official_air_date_cache(
    path: Path, media_id: int, episode: int, payload: dict[str, Any], identity=None
) -> None:
    cache = load_schedule_cache(path)
    cache["entries"][official_air_date_cache_key(media_id, episode, identity)] = {
        "expires_at": time.time() + SCHEDULE_CACHE_SECONDS,
        "official_air_date": payload,
    }
    save_schedule_cache(path, cache)


def metadata_identity_conflicts(base: ResolvedAnime, fresh: ResolvedAnime) -> list[str]:
    from .legacy_models import ResolvedAnime
    from .providers import canonical_season
    from .providers import infer_season
    from .queries import norm
    reasons = []
    for field_name in ("anilist_id", "bangumi_id"):
        old, new = getattr(base, field_name), getattr(fresh, field_name)
        if old and new and old != new:
            reasons.append(f"{field_name}_mismatch")
    expected = canonical_season(base.season or infer_season([base.title]))
    actual = canonical_season(fresh.season)
    if expected and actual and expected != actual:
        reasons.append("season_mismatch")
    source_names = fresh.metadata_titles or [fresh.title, *fresh.aliases]
    # A franchise title without a season cannot validate a numbered sequel.
    # An exact installment title permits unnumbered, named sequels.
    if expected and normalize_season_number(expected) > 1 and actual is None:
        if norm(base.title) not in {norm(n) for n in source_names}:
            reasons.append("season_unverified")
    if base.format in MAINLINE_FORMATS and fresh.format and fresh.format not in MAINLINE_FORMATS:
        reasons.append("format_mismatch")
    if "state" in base.source and fresh.metadata_titles:
        if not {norm(n) for n in [base.title, *base.aliases, *base.search_titles]} & {norm(n) for n in source_names}:
            reasons.append("work_title_mismatch")
    return reasons


def merge_resolved(base: ResolvedAnime, fresh: ResolvedAnime) -> ResolvedAnime:
    from .legacy_models import ResolvedAnime
    from .queries import unique
    reasons = metadata_identity_conflicts(base, fresh)
    if reasons or base.identity_conflicts or fresh.identity_conflicts:
        rejected = copy.deepcopy(base)
        rejected.identity_conflicts = [*base.identity_conflicts, *fresh.identity_conflicts]
        if reasons:
            rejected.identity_conflicts.append({"reasons": reasons, "expected_title": base.title,
                "expected_season": base.season, "received_title": fresh.title,
                "received_season": fresh.season, "anilist_id": fresh.anilist_id,
                "bangumi_id": fresh.bangumi_id, "source": fresh.source})
        return rejected
    fresh = copy.deepcopy(fresh)
    fresh.work_identity = base.work_identity or fresh.work_identity
    fresh.evidence = tuple({(e.provider, e.entry_id): e for e in (*base.evidence, *fresh.evidence)}.values())
    fresh.repair_proposal = base.repair_proposal or fresh.repair_proposal
    fresh.aliases = unique([*base.aliases, *fresh.aliases])
    fresh.search_titles = unique([*base.search_titles, *fresh.search_titles])
    fresh.verified_search_titles = unique([*base.verified_search_titles, *fresh.verified_search_titles])
    fresh.related_titles = unique([*base.related_titles, *fresh.related_titles])
    fresh.continuation_parts = fresh.continuation_parts or base.continuation_parts
    fresh.season = base.season or fresh.season
    if fresh.status == "FINISHED":
        fresh.trackable = fresh.current = False
    elif fresh.status is None:
        fresh.trackable = base.trackable or fresh.trackable
        fresh.current = base.current or fresh.current
    if not fresh.completion:
        fresh.completion = copy.deepcopy(base.completion)
    elif base.completion.get("confirmed") and (
        fresh.completion.get("confirmed") is not True
        or fresh.episodes != base.completion.get("final_episode")
    ):
        fresh.completion = {**fresh.completion, "conflict": True,
                            "previous_evidence": copy.deepcopy(base.completion)}
    fresh.bangumi_id = fresh.bangumi_id or base.bangumi_id
    fresh.anilist_id = fresh.anilist_id or base.anilist_id
    if base.source and base.source not in {"none", fresh.source}:
        fresh.source = f"{base.source}+{fresh.source}"
    if fresh.mainline_scope == "unknown":
        fresh.mainline_scope = base.mainline_scope
    return fresh


def metadata_queries(resolved: ResolvedAnime) -> list[str]:
    # Keep trusted translations first unless an explicit installment title is
    # needed to stop the provider from resolving the franchise's first season.
    from .legacy_models import ResolvedAnime
    from .providers import infer_season
    from .queries import unique
    preferred = [resolved.title] if infer_season([resolved.title]) else []
    return unique([*preferred, *resolved.search_titles, resolved.title, *resolved.aliases])


def hydrate_airing_metadata(
    resolved: ResolvedAnime,
    timeout: int,
    cache_path: Path,
    refresh_cache: bool,
    today: date,
) -> tuple[ResolvedAnime, str]:
    from .enrichment import enrich
    from .models import WorkIdentity
    from .evidence import part_of
    if resolved.work_identity is None:
        # Compatibility Python API has no record; still use the same fixed contract.
        resolved = copy.deepcopy(resolved)
        from .queries import norm
        resolved.work_identity = WorkIdentity('external:' + norm(resolved.title), resolved.title,
            resolved.season, part_of([resolved.title]), aliases=tuple(resolved.aliases), format=resolved.format)
    return enrich(resolved, timeout, cache_path, refresh_cache, today)


def ensure_official_air_identity(
    identity: IdentityResolution,
    cache_path: Path,
    timeout: int,
    refresh_cache: bool,
    today: date,
) -> IdentityResolution:
    """Resolve an AniList ID only when the official-air-date path still lacks one."""
    if identity.resolved.work_identity is not None:
        from .enrichment import enrich
        identity.resolved, identity.resolver = enrich(identity.resolved, timeout, cache_path, refresh_cache, today)
        return identity
    from .legacy_models import IdentityResolution
    from .legacy_models import ResolvedAnime
    from .queries import norm
    from .providers import resolve_title
    from .identity import resolver_failure
    from .queries import unique
    if identity.status == "ambiguous" or identity.resolved.anilist_id:
        return identity

    resolved = identity.resolved
    if not refresh_cache:
        for cached_name in unique([resolved.title, *resolved.search_titles, *resolved.aliases]):
            snapshot = read_schedule_snapshot(
                cache_path,
                f"title:{norm(cached_name)}",
            )
            if snapshot:
                cached = resolved_from_snapshot(snapshot, resolved)
                if cached.anilist_id:
                    return IdentityResolution(
                        "resolved",
                        merge_resolved(resolved, cached),
                        identity.state_show,
                        identity.tracked,
                        identity.input_kind,
                        unique([*identity.sources, "metadata_cache"]),
                        identity.failures,
                        "official_air_date_cache",
                    )

    ambiguous: ResolvedAnime | None = None
    failures = list(identity.failures)
    for query in metadata_queries(resolved)[:3]:
        status, fresh = resolve_title(query, timeout, today)
        if status == "resolved" and fresh and fresh.anilist_id:
            merged = merge_resolved(resolved, fresh)
            write_schedule_snapshots(
                cache_path,
                [schedule_cache_key(merged), f"title:{norm(resolved.title)}"],
                merged,
            )
            return IdentityResolution(
                "resolved",
                merged,
                identity.state_show,
                identity.tracked,
                identity.input_kind,
                unique([*identity.sources, "anilist"]),
                failures,
                "official_air_date_anilist",
            )
        if status == "ambiguous" and fresh:
            ambiguous = ambiguous or fresh
        else:
            failures.append(resolver_failure("anilist", fresh))

    if ambiguous is not None:
        return IdentityResolution(
            "ambiguous",
            merge_resolved(resolved, ambiguous),
            identity.state_show,
            identity.tracked,
            identity.input_kind,
            unique([*identity.sources, "anilist"]),
            failures,
            "official_air_date_ambiguous",
        )
    return IdentityResolution(
        identity.status,
        resolved,
        identity.state_show,
        identity.tracked,
        identity.input_kind,
        identity.sources,
        failures,
        "official_air_date_unavailable",
    )


def official_air_date_report(
    identity: IdentityResolution,
    episode: int,
    cache_path: Path,
    timeout: int,
    refresh_cache: bool,
    today: date,
) -> dict[str, Any]:
    from .legacy_models import IdentityResolution
    from .providers import anilist_air_date_request
    from .providers import anilist_media_request
    from .presentation import identity_conflict_report
    from .providers import media_to_resolved
    from .queries import unique
    resolved = identity.resolved
    if resolved.identity_conflicts:
        return identity_conflict_report(identity)
    base = {
        "title": resolved.title,
        "anilist_id": resolved.anilist_id,
        "episode": episode,
        "airing_at": None,
        "airing_date": None,
        "age_days": None,
        "is_current_airing": False,
        "is_current_new_anime": False,
        "series_start_date": None,
        "series_age_days": None,
        "scan_since": None,
        "scan_until": None,
        "window_mode": None,
        "recent_scan_eligible": False,
        "aliases": unique(
            [resolved.title, *resolved.search_titles, *resolved.aliases]
        ),
        "cache": "not_used",
        "failures": identity.failures[:2],
    }
    if identity.status == "ambiguous":
        return {
            **base,
            "status": "ambiguous",
            "choices": resolved.choices[:4],
        }
    if not resolved.anilist_id:
        return {**base, "status": "schedule_unavailable"}

    cache_payload = (
        None
        if refresh_cache
        else read_official_air_date_cache(cache_path, resolved.anilist_id, episode, resolved.work_identity)
    )
    cache_status = "hit" if cache_payload is not None else "miss"
    if cache_payload is None:
        try:
            data = anilist_air_date_request(resolved.anilist_id, episode, timeout)
            cache_payload = data.get("data") or {}
            if not isinstance(cache_payload, dict):
                cache_payload = {}
            if cache_payload:
                write_official_air_date_cache(
                    cache_path, resolved.anilist_id, episode, cache_payload, resolved.work_identity
                )
        except urllib.error.HTTPError as exc:
            exc.close()
            if exc.code != 404:
                return {
                    **base,
                    "status": "schedule_unavailable",
                    "cache": "unavailable",
                    "failures": [*base["failures"], str(exc)][:2],
                }
            try:
                media_data = anilist_media_request(
                    resolved.anilist_id,
                    timeout,
                )
                media_only = media_data.get("data", {}).get("Media")
                cache_payload = {
                    "Media": media_only,
                    "AiringSchedule": None,
                }
                if isinstance(media_only, dict):
                    write_official_air_date_cache(
                        cache_path,
                        resolved.anilist_id,
                        episode,
                        cache_payload,
                        resolved.work_identity,
                    )
            except (
                urllib.error.URLError,
                TimeoutError,
                json.JSONDecodeError,
                OSError,
            ) as media_exc:
                return {
                    **base,
                    "status": "schedule_unavailable",
                    "cache": "unavailable",
                    "failures": [*base["failures"], str(media_exc)][:2],
                }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            return {
                **base,
                "status": "schedule_unavailable",
                "cache": "unavailable",
                "failures": [*base["failures"], str(exc)][:2],
            }

    media = cache_payload.get("Media") if isinstance(cache_payload, dict) else None
    schedule = (
        cache_payload.get("AiringSchedule")
        if isinstance(cache_payload, dict)
        else None
    )
    if not isinstance(media, dict):
        return {**base, "status": "schedule_unavailable", "cache": cache_status}

    fresh, _ = media_to_resolved(resolved.title, media, today)
    checked = merge_resolved(resolved, fresh)
    if checked.identity_conflicts:
        return {**base, "status": "identity_conflict", "state_update": "none",
                "identity_conflicts": checked.identity_conflicts, "cache": cache_status}

    title_data = media.get("title") or {}
    aliases = unique(
        [
            resolved.title,
            title_data.get("english"),
            title_data.get("romaji"),
            title_data.get("native"),
            *(media.get("synonyms") or []),
            *resolved.search_titles,
            *resolved.aliases,
        ]
    )
    media_format = media.get("format")
    media_status = media.get("status")
    is_current_airing = (
        media_status == "RELEASING" and media_format in MAINLINE_FORMATS
    )
    start_data = media.get("startDate") or {}
    try:
        series_start_date = date(
            int(start_data["year"]),
            int(start_data["month"]),
            int(start_data["day"]),
        )
    except (KeyError, TypeError, ValueError):
        series_start_date = None
    series_age_days = (
        (today - series_start_date).days if series_start_date is not None else None
    )
    is_current_new_anime = bool(
        is_current_airing
        and series_age_days is not None
        and 0 <= series_age_days <= CURRENT_NEW_ANIME_MAX_AGE_DAYS
    )
    report = {
        **base,
        "anilist_id": media.get("id") or resolved.anilist_id,
        "format": media_format,
        "media_status": media_status,
        "is_current_airing": is_current_airing,
        "is_current_new_anime": is_current_new_anime,
        "series_start_date": (
            series_start_date.isoformat() if series_start_date is not None else None
        ),
        "series_age_days": series_age_days,
        "aliases": aliases,
        "cache": cache_status,
    }
    if not is_current_airing:
        return {**report, "status": "not_current_airing"}
    if not is_current_new_anime:
        return {**report, "status": "not_current_new_anime"}
    if (
        not isinstance(schedule, dict)
        or schedule.get("mediaId") != (media.get("id") or resolved.anilist_id)
        or schedule.get("episode") != episode
        or not isinstance(schedule.get("airingAt"), int)
    ):
        return {**report, "status": "schedule_unavailable"}

    airing_at = schedule["airingAt"]
    airing_date = datetime.fromtimestamp(airing_at).date()
    age_days = (today - airing_date).days
    report.update(
        {
            "airing_at": airing_at,
            "airing_date": airing_date.isoformat(),
            "age_days": age_days,
        }
    )
    if airing_at > int(time.time()) or age_days < 0:
        return {**report, "status": "not_aired_yet"}
    scan_until = min(today, airing_date + timedelta(days=7))
    return {
        **report,
        "status": "found",
        "scan_since": airing_date.isoformat(),
        "scan_until": scan_until.isoformat(),
        "window_mode": (
            "recent_to_today" if age_days <= 7 else "post_airing_7_day"
        ),
        "recent_scan_eligible": True,
    }


def next_airing_context(
    identity: IdentityResolution,
    episode: int,
    cache_path: Path,
    timeout: int,
    refresh_cache: bool,
    today: date,
) -> dict[str, Any]:
    """Distinguish an ordinary future airing from a verified schedule break."""
    from .legacy_models import IdentityResolution
    target = official_air_date_report(
        identity,
        episode,
        cache_path,
        timeout,
        refresh_cache,
        today,
    )
    context: dict[str, Any] = {
        "status": "schedule_unavailable",
        "episode": episode,
        "airing_at": target.get("airing_at"),
        "airing_date": target.get("airing_date"),
        "previous_episode": episode - 1 if episode > 1 else None,
        "previous_airing_at": None,
        "previous_airing_date": None,
        "gap_days": None,
        "weekly_break": False,
        "long_break": False,
        "skipped_weeks": 0,
    }
    if target.get("status") != "not_aired_yet" or not isinstance(target.get("airing_at"), int):
        return context
    context["status"] = "future_scheduled"
    if episode <= 1:
        return context

    previous = official_air_date_report(
        identity,
        episode - 1,
        cache_path,
        timeout,
        refresh_cache,
        today,
    )
    previous_airing_at = previous.get("airing_at")
    if not isinstance(previous_airing_at, int):
        return context
    gap_days = (target["airing_at"] - previous_airing_at) / 86400
    context.update(
        {
            "previous_airing_at": previous_airing_at,
            "previous_airing_date": previous.get("airing_date"),
            "gap_days": round(gap_days, 2),
        }
    )
    if gap_days >= 28:
        context["status"] = "long_break_unconfirmed"
        context["long_break"] = True
        context["skipped_weeks"] = max(1, round(gap_days / 7) - 1)
    elif gap_days >= 10.5:
        context["status"] = "weekly_break"
        context["weekly_break"] = True
        context["skipped_weeks"] = max(1, round(gap_days / 7) - 1)
    return context


def completed_part_context(
    resolved: ResolvedAnime,
    completed: int | None,
) -> dict[str, Any] | None:
    """Return a completed-part boundary before blindly searching the next episode number."""
    from .legacy_models import ResolvedAnime
    if (
        not completion_policy.confirmed(resolved)
        or not isinstance(resolved.episodes, int)
        or completed is None
        or completed < resolved.episodes
    ):
        return None
    parts = [part for part in resolved.continuation_parts if isinstance(part, dict)]
    explicit_parts = [part for part in parts if part.get("explicit_split_cour")]
    continuation = (explicit_parts or parts or [None])[0]
    if continuation is None:
        return {
            "status": "part_finished",
            "kind": "season_complete",
            "completed_episodes": resolved.episodes,
            "continuation": None,
        }
    next_airing_at = continuation.get("next_airing_at")
    return {
        "status": "split_cour_break" if continuation.get("explicit_split_cour") else "part_finished",
        "kind": "split_cour" if continuation.get("explicit_split_cour") else "sequel_scheduled",
        "completed_episodes": resolved.episodes,
        "continuation": continuation,
        "return_date": (
            datetime.fromtimestamp(next_airing_at).date().isoformat()
            if isinstance(next_airing_at, int)
            else continuation.get("start_date")
        ),
    }


def render_not_aired_reply(
    display_title: str,
    season: str | None,
    episode: int,
    airing: dict[str, Any],
) -> str:
    from .providers import canonical_season
    season_label = canonical_season(season) or "S01"
    target_label = f"{season_label}E{episode:02d}"
    airing_date = airing.get("airing_date")
    if airing.get("long_break"):
        return (
            f"《{display_title}》{target_label} 与上一集相隔 {airing.get('gap_days'):g} 天，"
            f"属于长休区间；官方目前排在 {airing_date}。尚无足够证据断言是临时停更还是分段放送。"
        )
    if airing.get("weekly_break"):
        skipped_weeks = int(airing.get("skipped_weeks") or 1)
        previous_date = airing.get("previous_airing_date")
        gap_days = airing.get("gap_days")
        detail = ""
        if previous_date and gap_days is not None:
            detail = f"，距上一集（{previous_date}）{gap_days:g} 天"
        return (
            f"《{display_title}》本周停更。{target_label} 官方安排在 {airing_date} 播出"
            f"{detail}，预计停更 {skipped_weeks} 周。"
        )
    if airing_date:
        return f"《{display_title}》{target_label} 尚未播出，官方安排在 {airing_date} 播出。"
    return f"《{display_title}》{target_label} 尚未播出，暂时无法取得可靠的下一次播出日期。"


def render_part_finished_reply(
    display_title: str,
    season: str | None,
    context: dict[str, Any],
) -> str:
    from .providers import canonical_season
    season_label = canonical_season(season) or "S01"
    completed = context.get("completed_episodes")
    continuation = context.get("continuation") or {}
    next_title = continuation.get("title")
    return_date = context.get("return_date")
    if context.get("status") == "split_cour_break":
        date_text = f"，预计 {return_date} 开始" if return_date else "，恢复日期尚未明确"
        return (
            f"《{display_title}》{season_label} 前半段已于第 {completed} 集结束。"
            f"官方续篇《{next_title}》属于后半段分批放送{date_text}。"
        )
    if next_title:
        date_text = f"，预计 {return_date} 开始" if return_date else ""
        return (
            f"《{display_title}》{season_label} 当前部分已于第 {completed} 集结束。"
            f"已确认后续《{next_title}》{date_text}；它不是本周临时停更。"
        )
    return (
        f"《{display_title}》{season_label} 当前部分已于第 {completed} 集结束。"
        "尚未确认后半段或续作排期，因此不继续按下一集编号搜索。"
    )


def latest_regular_target(
    resolved: ResolvedAnime,
    state_show: dict[str, Any] | None,
    *,
    use_state_fallback: bool = True,
) -> tuple[int | None, str]:
    from .legacy_models import ResolvedAnime
    now = int(time.time())
    if resolved.next_airing_episode and resolved.next_airing_at and resolved.next_airing_at > now:
        target = resolved.next_airing_episode - 1
        return (target, "anilist_schedule") if target > 0 else (None, "not_aired_yet")
    if resolved.status == "FINISHED" and resolved.episodes:
        # AniList's episode count is the planned/known season total, not
        # evidence that the final episode is currently available on Nyaa.
        # Let the latest-regular search establish the newest released episode
        # from qualified regular candidates instead of targeting the total.
        return None, "nyaa_discovery_required"
    if use_state_fallback and state_show and isinstance(state_show.get("latest_known_episode"), int):
        return state_show["latest_known_episode"], "observed_state_only"
    return None, "nyaa_discovery_required"

