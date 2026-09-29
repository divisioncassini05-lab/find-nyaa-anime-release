"""Extracted policy module: batch."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from typing import Any


def child_argv_from_args(args: argparse.Namespace, title: str) -> list[str]:
    child = [
        title,
        "--state",
        str(args.state),
        "--tier",
        args.tier,
        "--timeout",
        str(args.timeout),
        "--limit",
        str(args.limit),
        "--query-limit",
        str(args.query_limit),
        "--cache",
        str(args.cache),
        "--schedule-cache",
        str(args.schedule_cache),
        "--json",
        "--no-auto-batch",
    ]
    valued = (
        ("--season", args.season),
        ("--episode", args.episode),
        ("--min-gib-per-episode", args.min_gib_per_episode),
        ("--max-gib-per-episode", args.max_gib_per_episode),
    )
    for option, value in valued:
        if value is not None:
            child.extend([option, str(value)])
    for search_title in args.search_title or []:
        child.extend(["--search-title", search_title])
    for group_hint in args.release_group_hint or []:
        child.extend(["--release-group-hint", group_hint])
    if args.enqueue_qbittorrent:
        child.extend(["--qbittorrent-save-path", str(args.qbittorrent_save_path)])
        if args.qbittorrent_exe:
            child.extend(["--qbittorrent-exe", str(args.qbittorrent_exe)])
        if args.qbittorrent_profile:
            child.extend(["--qbittorrent-profile", str(args.qbittorrent_profile)])
        if args.qbittorrent_backup_dir:
            child.extend(["--qbittorrent-backup-dir", str(args.qbittorrent_backup_dir)])
    flags = (
        ("--refresh-cache", args.refresh_cache),
        ("--include-magnet", args.include_magnet),
        ("--include-page-link", args.include_page_link),
        ("--legal-ok", args.legal_ok),
        ("--no-web-resolve", args.no_web_resolve),
        ("--no-state-update", args.no_state_update),
        ("--mark-finished", args.mark_finished),
        ("--latest", args.latest),
        ("--whole-season", args.whole_season),
        ("--include-specials", args.include_specials),
        ("--explain", args.explain),
        ("--want-zh", args.want_zh),
        ("--require-zh", args.require_zh),
        ("--airing-priority", args.airing_priority),
        ("--allow-upward-compatibility", getattr(args, "allow_upward_compatibility", False)),
        ("--enqueue-qbittorrent", args.enqueue_qbittorrent),
    )
    child.extend(option for option, enabled in flags if enabled)
    return child


def render_batch_child_status(display_title: str, result: dict[str, Any]) -> str:
    from .providers import canonical_season
    target = result.get("target_episode")
    season = canonical_season(result.get("season")) or "S01"
    episode_label = f" {season}E{int(target):02d}" if isinstance(target, int) else ""
    status = result.get("status")
    messages = {
        "not_aired_yet": "尚未播出。",
        "airing_schedule_break": "本周期停更。",
        "long_break_unconfirmed": "进入长休区间，分段放送尚待确认。",
        "split_cour_break": "前半段已结束，等待后半段放送。",
        "part_finished": "当前部分已结束，等待后续排期。",
        "completed": "最终集已交付，本季追踪完成。",
        "needs_completion_review": "需核实官方结束日期及最终集数。",
        "no_rss_candidates": "没有检索到 Nyaa 发布。",
        "no_nyaa_release_for_target": "没有匹配目标集数的 Nyaa 发布。",
        "release_unqualified": "已有发布，但没有符合当前画质档位的资源。",
        "subtitle_unqualified": "已有发布，但没有经详细页确认的简体或繁体中文字幕资源。",
        "subtitle_check_incomplete": "中文字幕详情检查未完成，不能断言没有合格资源。",
        "needs_quality_fallback_confirmation": "轻量观看有中文字幕候选，需要确认是否降级。",
        "needs_quality_upgrade_confirmation": "存在完整高画质整季包，需要确认是否升级。",
        "needs_web_resolution": "需要网页补全可靠的英文或罗马字检索名。",
        "needs_confirmation": "候选身份存在歧义，需要确认。",
        "latest_unresolved": "无法可靠确认官方最新正篇。",
        "output_incomplete": "结果缺少必需输出字段，未作为成功结果返回。",
    }
    return f"《{display_title}》{episode_label} {messages.get(status, str(status))}"


def run_tracked_title_batch(args: argparse.Namespace, mentions: list[dict[str, Any]]) -> dict[str, Any]:
    from .cli import main
    results: list[dict[str, Any]] = []
    for mention in mentions:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            return_code = main(child_argv_from_args(args, mention["title"]))
        try:
            result = json.loads(output.getvalue())
        except json.JSONDecodeError:
            result = {
                "status": "batch_child_error",
                "resolved_title": mention["title"],
                "search_return_code": return_code,
                "search_stderr": output.getvalue()[-600:],
            }
        if not result.get("reply_text"):
            result["reply_text"] = render_batch_child_status(mention["title"], result)
        results.append(result)
    reply_text = "\n\n".join(result["reply_text"] for result in results)
    rendered_count = sum(bool(result.get("reply_text")) for result in results)
    return {
        "status": "batch",
        "titles": [mention["title"] for mention in mentions],
        "results": results,
        "reply_text": reply_text,
        "output_contract": {
            "ready": rendered_count == len(results) and all(
                result.get("status")
                not in {"found", "finished_deleted", "latest_unresolved", "latest_already_handled"}
                or result.get("output_contract", {}).get("ready", False)
                for result in results
            ),
            "result_count": len(results),
            "rendered_count": rendered_count,
        },
    }

