"""Bounded GET recovery for Nyaa pages and torrent metadata; TLS stays verified."""
from __future__ import annotations

import errno
import http.client
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


MAX_PAGE_BYTES = 32 * 1024 * 1024
_CA_OVERRIDES = ("SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE")


class TransportError(urllib.error.URLError):
    def __init__(self, code: str, attempts: list[dict], host: str | None):
        self.code = code
        self.attempts = attempts
        # No exception text, URLs with credentials, proxy credentials, or curl stderr.
        super().__init__(json.dumps({"code": code, "host": host, "attempts": attempts}))


def error_code(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"http_{exc.code}"
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "tls_certificate_verification_failed"
    if isinstance(reason, ssl.SSLEOFError):
        return "tls_unexpected_eof"
    if isinstance(reason, ssl.SSLError):
        return "tls_handshake_failed"
    if isinstance(reason, (TimeoutError, socket.timeout, subprocess.TimeoutExpired)):
        return "timeout"
    if isinstance(reason, socket.gaierror):
        return "dns_failed"
    if isinstance(reason, PermissionError):
        return "permission_denied"
    if isinstance(reason, http.client.IncompleteRead):
        return "response_incomplete"
    if isinstance(reason, ConnectionError) or getattr(reason, "errno", None) in {
        errno.ECONNRESET, errno.ECONNABORTED, errno.ECONNREFUSED, errno.ENETUNREACH,
        errno.EHOSTUNREACH, 10053, 10054, 10061,
    }:
        return "connection_failed"
    return "network_error"


_TRANSIENT = {"tls_unexpected_eof", "timeout", "dns_failed", "response_incomplete",
              "connection_failed", "http_502", "http_503", "http_504"}
_TLS = {"tls_unexpected_eof", "tls_certificate_verification_failed", "tls_handshake_failed"}


def native_curl_path() -> str | None:
    """Use the Windows inbox TLS backend only, and honor explicit trust overrides."""
    if sys.platform != "win32" or any(os.environ.get(k) for k in _CA_OVERRIDES):
        return None
    root = os.environ.get("SystemRoot")
    path = Path(root) / "System32" / "curl.exe" if root else None
    return str(path) if path and path.is_file() else None


def proxy_for(url: str) -> str:
    parsed = urlsplit(url)
    if urllib.request.proxy_bypass(parsed.hostname or ""):
        return ""
    # Match urllib, including Windows registry/environment selection. Do not silently
    # switch to curl's ALL_PROXY interpretation or bypass a configured proxy.
    return urllib.request.getproxies().get(parsed.scheme, "")


def native_get(request, timeout: float, max_bytes: int, executable: str) -> tuple[bytes, None]:
    parsed = urlsplit(request.full_url)
    if parsed.scheme != "https" or parsed.hostname != "nyaa.si" or parsed.username or parsed.password:
        raise TransportError("native_url_not_allowed", [], parsed.hostname)
    command = [executable, "--disable", "--silent", "--show-error", "--fail",
               "--location", "--max-redirs", "3", "--proto", "=https",
               "--proto-redir", "=https", "--compressed", "--max-time", str(timeout),
               "--max-filesize", str(max_bytes), "--proxy", proxy_for(request.full_url),
               "--noproxy", ""]
    for key, value in request.header_items():
        command.extend(["--header", f"{key}: {value}"])
    command.extend(["--url", request.full_url])
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TransportError(error_code(exc), [], parsed.hostname) from None
    if result.returncode:
        code = {60: "tls_certificate_verification_failed", 35: "tls_handshake_failed",
                28: "timeout", 5: "proxy_dns_failed", 6: "dns_failed", 7: "connection_failed",
                22: "http_error", 63: "response_too_large"}.get(result.returncode, "native_network_error")
        # Keep only allowlisted Schannel symbols, never raw stderr or proxy secrets.
        symbols = re.findall(r'\bSEC_E_[A-Z_]+\b', result.stderr.decode('utf-8', 'replace'))
        if 'SEC_E_NO_CREDENTIALS' in symbols:
            code = 'tls_user_context_unavailable'
        attempt = {"backend": "windows_curl", "exit_code": result.returncode, "code": code}
        if symbols:
            attempt['tls_codes'] = sorted(set(symbols))
        raise TransportError(code, [attempt], parsed.hostname)
    if len(result.stdout) > max_bytes:
        raise TransportError("response_too_large", [], parsed.hostname)
    return result.stdout, None  # curl --compressed already decodes Content-Encoding.


def fetch_bytes(request, *, timeout: float, max_bytes: int = MAX_PAGE_BYTES,
                opener=None, native_fallback: bool = True) -> tuple[bytes, str | None]:
    """At most two urllib GETs and one Windows GET within a shared recovery budget.

    Never retry client submissions, permission failures, 4xx, or certificate failures
    on the same backend. A certificate error may use Windows' independent verified
    trust backend once; it must also pass verification. No trust stores are changed.
    """
    if request.get_method() != "GET":
        raise ValueError("Recovery transport accepts GET only")
    opener = opener or urllib.request.urlopen
    host = urlsplit(request.full_url).hostname
    started = time.monotonic()
    deadline = started + max(0.001, timeout)
    attempts: list[dict] = []
    last_code = "timeout"
    native_path = native_curl_path() if native_fallback else None
    for number in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        # Reserve time for recovery rather than letting the first timeout consume it.
        slots = (2 - number) + bool(native_path)
        attempt_timeout = remaining / slots
        try:
            with opener(request, timeout=attempt_timeout) as response:
                payload = response.read(max_bytes + 1)
                headers = getattr(response, "headers", {})
                encoding = headers.get("Content-Encoding")
            if len(payload) > max_bytes:
                raise TransportError("response_too_large", attempts, host)
            if time.monotonic() > deadline:
                raise TimeoutError("response exceeded recovery budget")
            if attempts:
                _recovered(host, attempts, "urllib")
            return payload, encoding
        except urllib.error.HTTPError as exc:
            last_code = error_code(exc)
            if last_code not in _TRANSIENT:
                raise  # Preserve 404/403 semantics for callers.
            exc.close()
        except TransportError:
            raise
        except (OSError, http.client.IncompleteRead) as exc:
            last_code = error_code(exc)
        attempts.append({"backend": "urllib", "code": last_code})
        if last_code not in _TRANSIENT:
            break
        if number == 0:
            time.sleep(min(0.2, max(0.0, deadline - time.monotonic()) / 10))
    remaining = deadline - time.monotonic()
    if native_path and remaining > 0 and last_code in (_TRANSIENT | _TLS):
        try:
            result = native_get(request, remaining, max_bytes, native_path)
        except TransportError as exc:
            attempts.extend(exc.attempts or [{"backend": "windows_curl", "code": exc.code}])
            last_code = exc.code
        else:
            _recovered(host, attempts, "windows_curl")
            return result
    raise TransportError(last_code, attempts, host)


def _recovered(host, attempts, backend):
    print(json.dumps({"transport_recovery": {"host": host, "failed_attempts": attempts,
                     "recovered_with": backend, "tls_verification": "enabled"}}), file=sys.stderr)
