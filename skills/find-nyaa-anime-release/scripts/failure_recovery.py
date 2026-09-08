"""Read-only recovery guidance. Scheduling authority stays with the originating prompt."""

from typing import Any


def recovery_plan(report: dict[str, Any]) -> dict[str, Any]:
    status = report.get("status")
    diagnostic = report.get("diagnostic") or {}
    selected = report.get("selected") or {}
    client = report.get("qbittorrent") or {}
    target_observed = bool(diagnostic.get("target_candidate_count"))
    released = target_observed or bool(selected and status in {
        "found", "finished_deleted", "latest_already_handled", "download_enqueue_failed",
    })
    result: dict[str, Any] = {
        "stage": "none", "action": "stop", "retry_basis": None,
        "release_confirmed": released,
        "latest_confirmed": bool(
            report.get("intent") == "latest_regular"
            and isinstance(report.get("target_episode"), int)
            and status not in {"latest_unresolved", "needs_confirmation", "needs_web_resolution"}
        ),
        "scheduled_retry_requires_prompt_authorization": True,
    }
    if status in {"found", "finished_deleted", "latest_already_handled", "not_aired_yet",
                  "airing_schedule_break", "long_break_unconfirmed", "split_cour_break",
                  "part_finished"}:
        return result
    if status == "download_enqueue_failed":
        result.update(stage="client", action="diagnose_client", error_code=client.get("error_code"))
        if client.get("retryable") is True:
            result["retry_basis"] = "client_transient"
        # Do not silently equate a local client failure with a network outage.
        # Even a transient client error needs explicit inclusion in the parent's retry rule.
        return result
    if status in {"needs_confirmation", "needs_web_resolution", "needs_quality_fallback_confirmation",
                  "needs_quality_upgrade_confirmation", "candidate_id_title_mismatch"}:
        result.update(stage="identity_or_constraints", action="resolve_identity_or_choice")
        return result
    if status == "output_incomplete":
        result.update(stage="verification", action="verify_missing_fields")
        return result
    if status in {"subtitle_check_incomplete", "season_check_incomplete"}:
        result.update(stage="verification", action="verify_one_distinct_backup", retry_basis="detail")
        return result
    if status == "network_error" or (status == "latest_unresolved" and diagnostic.get("rss_failure_count")):
        result.update(stage="discovery", action="retry_failed_queries_once", retry_basis="network")
        return result
    if status == "latest_unresolved":
        result.update(stage="discovery", action="establish_latest_with_verified_latin_title")
        return result
    if status in {"no_rss_candidates", "no_nyaa_release_for_target", "release_unqualified",
                  "subtitle_unqualified", "no_complete_season_release", "candidate_not_found"}:
        result.update(stage="discovery", action="bounded_supplement_then_eligible_rescue")
        if released:
            result["retry_basis"] = "resource_availability"
        result["searched_without_qualified_result"] = True
        result["airing_is_not_release_evidence"] = not released
        return result
    result.update(stage="unknown", action="inspect_error")
    return result
