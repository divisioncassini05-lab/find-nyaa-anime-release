"""Extracted policy module: presentation."""

from __future__ import annotations

import argparse
import re
from datetime import date
from typing import Any

from airing_watch_state import completed_episode
from release_search_core import SearchIntent


import completion as completion_policy


def selected_view(
    candidate: dict[str, Any] | None,
    include_page_link: bool,
    require_zh: bool = False,
) -> dict[str, Any] | None:
    if not candidate:
        return None
    selected = {
        "title": candidate.get("title"),
        "size": candidate.get("size"),
        "seeders": candidate.get("seeders"),
        "resolution": candidate.get("resolution"),
        "tier_fit": candidate.get("tier_fit"),
        "magnet": candidate.get("magnet"),
        "subtitle_signal": candidate.get("subtitle_signal"),
        "detail_chinese_confirmed": candidate.get("detail_chinese_confirmed"),
        "detail_subtitle_signal": candidate.get("detail_subtitle_signal"),
        "score": candidate.get("score"),
        "effective_season": candidate.get("effective_season"),
        "season_source": candidate.get("season_source"),
        "work_match": candidate.get("work_match"),
        "coverage": candidate.get("coverage"),
    }
    if candidate.get("work_match_evidence") is not None:
        selected["work_match_evidence"] = candidate["work_match_evidence"]
    if include_page_link or require_zh:
        selected["url"] = candidate.get("url")
    return selected


def is_final_episode(resolved: ResolvedAnime | None, episode: int | None) -> bool:
    from .legacy_models import ResolvedAnime
    if not resolved or episode is None:
        return False
    return bool(completion_policy.confirmed(resolved) and episode == resolved.episodes)


def result_output_contract(
    selected: dict[str, Any] | None,
    include_magnet: bool,
    require_zh: bool = False,
) -> dict[str, Any]:
    required = ["title", "size", "seeders"]
    if include_magnet:
        required.append("magnet")
    if require_zh:
        required.extend(["url", "detail_chinese_confirmed", "detail_subtitle_signal"])
    missing = []
    for field_name in required:
        value = (selected or {}).get(field_name)
        if value is None or value == "" or (field_name == "detail_chinese_confirmed" and value is not True):
            missing.append(field_name)
    return {
        "ready": not missing,
        "magnet_requested": include_magnet,
        "required_fields": required,
        "missing_fields": missing,
    }


def quality_compatibility(
    selected: dict[str, Any] | None,
    args: argparse.Namespace,
) -> str | None:
    """Describe an accepted release above a named tier's preferred band."""
    if not selected or not getattr(args, "allow_upward_compatibility", False):
        return None
    if getattr(args, "size_policy_source", "tier") != "tier":
        return None
    return "upward" if selected.get("tier_fit") == "above" else None


def render_result_reply(
    display_title: str,
    season: str | None,
    episode: int | None,
    selected: dict[str, Any],
    include_magnet: bool,
) -> str:
    from .providers import canonical_season
    episode_label = ""
    if episode is not None:
        season_label = canonical_season(season) or "S01"
        episode_label = f" {season_label}E{episode:02d}"
    subtitle = selected.get("subtitle_signal") or "字幕未确认"
    if str(subtitle).casefold() in {"not confirmed", "unknown", "none"}:
        subtitle = "字幕未确认"
    lines = [
        f"《{display_title}》{episode_label}",
        str(selected.get("title") or ""),
        f"{selected.get('size')} | {selected.get('seeders')} 做种 | {subtitle}",
    ]
    if selected.get("url"):
        lines.append(f"Nyaa: {selected['url']}")
    if include_magnet:
        lines.extend(["", "```text", str(selected.get("magnet") or ""), "```"])
    return "\n".join(lines)


def render_latest_already_handled_reply(
    display_title: str,
    season: str | None,
    latest_episode: int,
    next_episode: int,
    qbittorrent_requested: bool,
) -> str:
    from .providers import canonical_season
    season_label = canonical_season(season) or "S01"
    lines = [
        f"《{display_title}》{season_label}E{latest_episode:02d} 是目前最新正篇。",
        f"追番进度已到 {season_label}E{latest_episode:02d}；下一目标是 {season_label}E{next_episode:02d}。",
        "本轮没有新的正篇。",
    ]
    if qbittorrent_requested:
        lines.append("未调用 qBittorrent；已有追番进度不能证明下载任务当前存在。")
    return "\n".join(lines)


def render_season_batch_reply(
    display_title: str,
    season: str | None,
    selected: dict[str, Any],
    include_magnet: bool,
) -> str:
    from .providers import canonical_season
    coverage = selected.get("coverage") or {}
    season_label = canonical_season(season) or "S01"
    episode_count = coverage.get("expected_episodes")
    scope_label = "精确单季包" if coverage.get("scope") == "exact" else "含目标季的多季合集"
    minimum = coverage.get("min_gib_per_episode")
    maximum = coverage.get("max_gib_per_episode")
    average = coverage.get("average_gib_per_episode")
    quality_basis = coverage.get("quality_basis")
    if quality_basis == "source_exempt" or coverage.get("source_exempt"):
        size_range = "BDMV/Remux 高画质来源"
    elif quality_basis == "average" and average is not None:
        size_range = f"平均 {average:g} GiB/集（范围 {minimum:g}-{maximum:g}）"
    elif minimum is not None and maximum is not None:
        size_range = f"逐集 {minimum:g}-{maximum:g} GiB"
    else:
        size_range = "逐集体积已核验"
    lines = [
        f"《{display_title}》{season_label} 整季",
        str(selected.get("title") or ""),
        f"{scope_label} | {episode_count or '?'} 集 | {size_range} | {selected.get('seeders')} 做种",
    ]
    if selected.get("url"):
        lines.append(f"Nyaa: {selected['url']}")
    if include_magnet:
        lines.extend(["", "```text", str(selected.get("magnet") or ""), "```"])
    return "\n".join(lines)


def render_failure_reply(
    status: str,
    display_title: str,
    season: str | None,
    intent: SearchIntent,
    tier: str,
    diagnostic: dict[str, Any] | None = None,
    target_episode: int | None = None,
) -> str:
    from .providers import canonical_season
    season_label = canonical_season(season) or "S01"
    subject = f"《{display_title}》{season_label} 整季" if intent is SearchIntent.SEASON_BATCH else f"《{display_title}》"
    if intent is not SearchIntent.SEASON_BATCH and target_episode is not None:
        subject += f" {season_label}E{target_episode:02d}"
    tier_label = {"browse": "轻量观看", "watch": "普通观看", "premium": "高画质"}.get(tier, tier)
    if (diagnostic or {}).get("network", {}).get("error_code") == "tls_certificate_verify_failed":
        return f"{subject}的 HTTPS 证书校验失败，需检查证书信任、代理和执行环境；本轮检索不完整，不能据此判断资源不存在。"
    size_policy = (diagnostic or {}).get("size_policy") or {}
    has_above_range_release = (
        intent is not SearchIntent.SEASON_BATCH
        and size_policy.get("hard_max_gib") is not None
        and int((diagnostic or {}).get("above_max_count") or 0) > 0
    )
    if has_above_range_release:
        release_unqualified = f"{subject}当前区间内没有合格资源，但有高于该区间的资源可选。"
    elif intent is SearchIntent.SEASON_BATCH:
        reasons = []
        if int((diagnostic or {}).get("aggregate_floor_rejected_count") or 0) > 0:
            reasons.append(f"整季总大小不足以让正篇平均值达到{tier_label}最低线")
        if int((diagnostic or {}).get("absolute_floor_rejected_count") or 0) > 0:
            reasons.append("至少一个正篇文件低于 1 GiB 绝对底线")
        if int((diagnostic or {}).get("average_range_rejected_count") or 0) > 0:
            reasons.append(f"正篇平均体积不在{tier_label}档位")
        if int((diagnostic or {}).get("explicit_per_file_rejected_count") or 0) > 0:
            reasons.append("至少一个正篇文件不满足你明确给出的体积范围")
        detail = "；".join(reasons) or f"正篇平均体积不符合{tier_label}档位"
        release_unqualified = f"{subject}存在对应发布，但{detail}；未达门槛的候选不会展示。"
    else:
        release_unqualified = f"{subject}存在对应发布，但没有资源满足{tier_label}档位。"
    messages = {
        "no_complete_season_release": f"{subject}没有找到覆盖完整目标季且通过核验的资源包。",
        "season_check_incomplete": f"{subject}存在整季候选，但文件列表或逐集覆盖尚未核验完成，因此没有返回磁力链接。",
        "release_unqualified": release_unqualified,
        "no_rss_candidates": f"{subject}没有检索到 Nyaa 原始候选。",
        "no_nyaa_release_for_target": f"{subject}没有检索到目标正篇发布。",
        "candidate_not_found": f"{subject}未找到指定的 Nyaa 发布；未替换为其他资源。",
        "candidate_id_title_mismatch": f"{subject}指定的 Nyaa 发布与作品不匹配；未提交下载。",
        "subtitle_unqualified": f"{subject}的画质合格候选均未确认带有中文字幕。",
        "subtitle_check_incomplete": f"{subject}的中文字幕检查尚未完成，因此没有返回磁力链接。",
        "latest_unresolved": f"{subject}目前无法可靠确认最新正篇。",
        "network_error": f"{subject}检索时网络请求失败，请稍后重试。",
        "output_incomplete": f"{subject}的结果缺少必要字段，因此没有输出不完整的资源信息。",
        "download_enqueue_failed": f"{subject}已找到合格资源，但 qBittorrent 入队失败；进度未推进。请根据下载器错误排查，不要重新解释为找不到资源。",
    }
    return messages.get(status, status)


def render_quality_fallback_question(
    display_title: str,
    season: str | None,
    episode: int | None,
    candidate: dict[str, Any],
) -> str:
    from .providers import canonical_season
    season_label = canonical_season(season) or "S01"
    episode_label = f" {season_label}E{episode:02d}" if episode is not None else ""
    subtitle = candidate.get("subtitle_signal") or "中文字幕已确认"
    return "\n".join(
        [
            f"《{display_title}》{episode_label} 的普通观看档没有同时满足画质和中文字幕要求的资源。",
            "轻量观看档找到了这个候选：",
            str(candidate.get("title") or ""),
            f"{candidate.get('size')} | {candidate.get('seeders')} 做种 | {subtitle}",
            "是否降级到轻量观看？",
        ]
    )


def premium_source_type(candidate: dict[str, Any]) -> str:
    title = str(candidate.get("title") or "")
    if re.search(r"(?<![a-z0-9])bdmv(?![a-z0-9])", title, re.I):
        return "BDMV"
    if re.search(r"(?<![a-z0-9])remux(?![a-z0-9])", title, re.I):
        return "Remux"
    return "高码率压制"


def render_quality_upgrade_question(
    display_title: str,
    season: str | None,
    candidate: dict[str, Any],
) -> str:
    from .providers import canonical_season
    coverage = candidate.get("coverage") or {}
    season_label = canonical_season(season) or "S01"
    episode_count = coverage.get("expected_episodes") or coverage.get("main_file_count") or "?"
    source_type = candidate.get("source_type") or premium_source_type(candidate)
    return "\n".join(
        [
            f"《{display_title}》{season_label} 整季没有合格的普通观看或轻量观看资源。",
            f"发现一个完整的高画质 {source_type}：{candidate.get('size')} | {episode_count} 集 | "
            f"{candidate.get('seeders')} 做种。",
            "是否改用高画质？",
        ]
    )


def identity_conflict_report(identity: IdentityResolution) -> dict[str, Any]:
    from .legacy_models import IdentityResolution
    resolved = identity.resolved
    return {"status": "identity_conflict", "identity_status": "identity_conflict",
            "resolved_title": resolved.title, "season": resolved.season,
            "tracked": identity.tracked, "target_episode": None, "selected": None,
            "identity_conflicts": resolved.identity_conflicts, "state_update": "none",
            "stage_errors": resolved.stage_errors, "repair_evidence": resolved.repair_proposal,
            "work_identity": {"track_id": resolved.work_identity.track_id if resolved.work_identity else None,
                "season": resolved.work_identity.season if resolved.work_identity else resolved.season,
                "identity_revision": resolved.work_identity.revision if resolved.work_identity else None},
            "diagnostic": {"search_skipped": "metadata_identity_conflict"},
            "qbittorrent": {"status": "not_attempted", "reason": "metadata_identity_conflict"},
            "reply_text": f"《{resolved.title}》的外部元数据与追番记录身份冲突，需核验同一作品/季度的条目；进度未变。"}


def identity_report_fields(
    identity: IdentityResolution,
    season: str | None,
    search_titles: list[str] | None = None,
    status_override: str | None = None,
) -> dict[str, Any]:
    from .legacy_models import IdentityResolution
    resolved = identity.resolved
    return {
        "identity_status": "identity_conflict" if resolved.identity_conflicts else status_override or identity.status,
        "identity_conflicts": resolved.identity_conflicts,
        "repair_evidence": resolved.repair_proposal,
        "stage_errors": resolved.stage_errors,
        "input_kind": identity.input_kind,
        "work_identity": {
            "track_id": resolved.work_identity.track_id if resolved.work_identity else None,
            "identity_revision": resolved.work_identity.revision if resolved.work_identity else None,
            "part": resolved.work_identity.part if resolved.work_identity else None,
            "bangumi_id": resolved.bangumi_id,
            "anilist_id": resolved.anilist_id,
            "format": resolved.format,
            "season": season or resolved.season,
        },
        "search_titles": search_titles if search_titles is not None else resolved.search_titles,
        "identity_sources": identity.sources,
        "resolver_failures": identity.failures,
        "completion": resolved.completion,
        "completion_review": {
            "reasons": completion_policy.review_reasons(resolved, completed_episode(identity.state_show), date.today()),
            "end_date_missing": not resolved.completion.get("end_date"),
        },
    }

