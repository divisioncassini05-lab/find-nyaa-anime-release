"""Read-only recovery guidance. Scheduling authority stays with the originating prompt."""

import re
from typing import Any
import json


def transport_diagnostic(report: dict[str, Any]) -> dict[str, Any]:
    """Read transport evidence, not release titles or arbitrary candidate prose."""
    run = report.get("search_run") or {}
    diag = report.get("diagnostic") or {}
    evidence = [report.get("failures"), report.get("search_stderr"), report.get("resolver_failures"),
                run.get("errors"), [r.get("error") for r in run.get("requests", [])],
                diag.get("detail_failures"), diag.get("network"), diag.get('candidate_id_direct_failures')]
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
    errors = list(strings(evidence))
    codes = {code for error in errors for code in re.findall(r'"code"\s*:\s*"([a-z0-9_]+)"', error)}
    if codes & {'permission_denied', 'tls_user_context_unavailable'}:
        return {'error_code': 'tls_user_context_unavailable' if 'tls_user_context_unavailable' in codes else 'permission_denied',
                'error_codes': sorted(codes), 'retryable': False,
                'action': 'request_approved_execution_context', 'verification_required': True}
    if 'tls_certificate_verification_failed' in codes:
        return {'error_code': 'tls_certificate_verify_failed', 'retryable': False,
                'action': 'inspect_tls_trust_and_execution_context', 'verification_required': True}
    text = json.dumps(evidence, ensure_ascii=False).casefold()
    if "certificate_verify_failed" in text or "nyaatlsverificationerror" in text:
        return {"error_code": "tls_certificate_verify_failed", "retryable": False,
                "action": "inspect_tls_trust_and_execution_context", "verification_required": True}
    if any('"attempts"' in error for error in errors):
        return {'error_code': 'transport_recovery_exhausted', 'error_codes': sorted(codes),
                'retryable': False, 'action': 'diagnose_exhausted_transport', 'verification_required': True}
    return {}


def recovery_plan(report: dict[str, Any]) -> dict[str, Any]:
    status = report.get("status")
    diagnostic = report.get("diagnostic") or {}
    selected = report.get("selected") or {}
    client = report.get("qbittorrent") or {}
    supplement = diagnostic.get('strict_zh_supplement') or {}
    primary = supplement.get('primary_diagnostics') or {}
    target_observed = bool(diagnostic.get("target_candidate_count") or primary.get('target_candidate_count'))
    released = target_observed or bool(selected and status in {
        "found", "finished_deleted", "completed", "latest_already_handled", "download_enqueue_failed",
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
    if status in {'client_context_required', 'client_context_unverified'} or client.get('error_code') in {
        'client_context_required', 'client_context_unverified'
    }:
        code = client.get('error_code') or status
        result.update(stage='client_context', error_code=code,
                      action='run_full_resolver_in_approved_user_context' if code == 'client_context_required'
                      else 'inspect_execution_context', retry_basis=None,
                      release_confirmed=bool(selected), requires_execution_tool_approval=True)
        return result
    if status == "identity_conflict":
        result.update(stage="identity", action="verify_tracked_work_metadata", retry_basis=None)
        return result
    transport = transport_diagnostic(report)
    if transport:
        result.update(stage="transport", **transport, retry_basis=None,
                      release_confirmed=False, latest_confirmed=False)
        return result
    if status == "needs_completion_review":
        result.update(stage="broadcast_metadata", action="verify_official_completion_evidence")
        return result
    if status in {"found", "finished_deleted", "completed", "latest_already_handled", "not_aired_yet",
                  "airing_schedule_break", "long_break_unconfirmed", "split_cour_break",
                  "part_finished"}:
        return result
    if status in {"download_enqueue_failed", "available_enqueue_failed"}:
        client_code = client.get("error_code")
        if client_code in {"startup_exited_without_client", "handoff_unverified", "client_context_required"}:
            result.update(
                stage="client_context",
                action="retry_full_resolver_in_approved_user_context",
                error_code=client_code,
                retry_basis=None,
                scheduled_retry_allowed=False,
                requires_execution_tool_approval=True,
                recheck_acceptance_before_submission=True,
            )
            return result
        result.update(stage="client", action="diagnose_client", error_code=client_code)
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
        result['latest_confirmed'] = False
        result.update(stage="discovery", action="retry_failed_queries_once", retry_basis="network")
        return result
    if status == "latest_unresolved":
        result.update(stage="discovery", action="establish_latest_with_verified_latin_title")
        return result
    if status in {"no_rss_candidates", "no_nyaa_release_for_target", "release_unqualified",
                  "subtitle_unqualified", "no_complete_season_release", "candidate_not_found"}:
        result.update(stage="discovery", action="bounded_supplement_then_eligible_rescue")
        if supplement.get('attempted'):
            result['action'] = 'eligible_official_date_rescue'
            result['strict_zh_supplement_completed'] = True
        if released:
            result["retry_basis"] = "resource_availability"
        result["searched_without_qualified_result"] = True
        result["airing_is_not_release_evidence"] = not released
        return result
    result.update(stage="unknown", action="inspect_error")
    return result
