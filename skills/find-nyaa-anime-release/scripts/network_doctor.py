"""Bounded, read-only Nyaa connectivity diagnosis; never changes routes or submits."""
from __future__ import annotations

import json
import socket
import time
import urllib.request
from urllib.parse import urlsplit

from http_transport import TransportError, error_code, proxy_for
from nyaa_client import NyaaClient


def proxy_summary(url="https://nyaa.si/"):
    value = proxy_for(url)
    if not value:
        return {"configured": False}
    parsed = urlsplit(value if "://" in value else "http://" + value)
    # Credentials, bypass lists and subscription URLs must never be emitted.
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return {"configured": True, "configuration_error": "invalid_proxy_port"}
    return {"configured": True, "scheme": parsed.scheme,
            "host": parsed.hostname, "port": port}


def diagnose(*, client=None, connect=socket.create_connection):
    report = {"target": "nyaa.si", "proxy": proxy_summary(), "read_only": True}
    proxy = report["proxy"]
    if proxy.get("configuration_error"):
        return dict(report, status="proxy_configuration_error")
    if proxy.get("configured"):
        try:
            with connect((proxy["host"], proxy["port"]), timeout=2):
                pass
            proxy["tcp_reachable"] = True
        except OSError as exc:
            proxy["tcp_reachable"] = False
            return dict(report, status="proxy_unreachable", error_code=error_code(exc))
    started = time.monotonic()
    try:
        page = (client or NyaaClient()).fetch_listing(
            "", "1_0", "0", 1, 18)
        # HTTP 200 is insufficient: a challenge or error page is not a listing.
        if "torrent-list" in page and "Nyaa" in page:
            report["status"] = "nyaa_listing_reachable"
        else:
            report["status"] = "unexpected_page"
            report["challenge_marker"] = any(
                marker in page.lower() for marker in ("cf-chl-", "challenge-platform"))
    except Exception as exc:
        cause = exc
        while cause.__cause__ is not None and not isinstance(cause, TransportError):
            cause = cause.__cause__
        report["status"] = "request_failed"
        report["error_type"] = type(exc).__name__
        report["error_code"] = getattr(cause, "code", None) or error_code(cause)
        if isinstance(cause, TransportError):
            report["attempts"] = cause.attempts
            report["scheduled_outcome"] = cause.scheduled_outcome
        # Never print raw exception text: proxy errors may contain credentials.
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report["note"] = "TCP reachability does not establish proxy egress health."
    return report


if __name__ == "__main__":
    print(json.dumps(diagnose(), ensure_ascii=False, indent=2))
