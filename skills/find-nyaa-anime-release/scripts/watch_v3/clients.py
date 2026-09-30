"""Download-client port; acceptance contracts and bounded recovery actions."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError, URLError
from http.cookiejar import CookieJar
from .store import SUCCESS_STATUSES

@dataclass(frozen=True)
class RecoveryAction:
    error_code: str
    retryable: bool
    next_action: str = 'recover_same_operation'
    same_hash_recovery_allowed: bool = True
    scheduled_retry_allowed: bool = False
    requires_execution_tool_approval: bool = False

class ClientFailure(RuntimeError):
    def __init__(self, code, *, retryable=False, details=None):
        super().__init__(code)
        self.recovery = RecoveryAction(code, retryable,
            requires_execution_tool_approval=code in {'client_context_required','startup_unverified','handoff_unverified','permission_denied'})
        self.details = details or {}

@dataclass(frozen=True)
class ClientContext:
    name: str
    verified: bool
    details: dict = field(default_factory=dict)

@dataclass(frozen=True)
class DeliveryRequest:
    track_id: str
    operation_id: str
    info_hash: str
    magnet: str
    save_path: str | None = None
    source_url: str | None = None
    torrent_path: str | None = None

    @property
    def idempotency_key(self):
        return f'{self.track_id}:{self.operation_id}:{self.info_hash.lower()}'

    def validate(self):
        from qbittorrent_submit import extract_btih, torrent_info_hash
        if self.torrent_path:
            if torrent_info_hash(Path(self.torrent_path).read_bytes()) != self.info_hash:
                raise ClientFailure('torrent_hash_mismatch')
        elif extract_btih(self.magnet) != self.info_hash:
            raise ClientFailure('magnet_hash_mismatch')
        if not self.operation_id or not self.track_id:
            raise ClientFailure('invalid_delivery_request')

@dataclass(frozen=True)
class AcceptanceEvidence:
    info_hash: str
    verified: bool
    details: dict = field(default_factory=dict)

@dataclass(frozen=True)
class DeliveryReceipt:
    operation_id: str
    info_hash: str
    status: str
    accepted: bool
    evidence: AcceptanceEvidence
    track_id: str = ''

    def validate(self, request):
        if (not self.accepted or self.status not in SUCCESS_STATUSES or self.operation_id != request.operation_id
                or self.info_hash != request.info_hash or self.track_id != request.track_id
                or self.evidence.info_hash != request.info_hash):
            raise ClientFailure('invalid_acceptance_receipt')
        return self

class DownloadClient(Protocol):
    def preflight(self) -> ClientContext: ...
    def submit(self, request: DeliveryRequest) -> DeliveryReceipt: ...
    def inspect(self, info_hash: str) -> AcceptanceEvidence: ...


def receipt(request, status, evidence):
    return DeliveryReceipt(request.operation_id, request.info_hash, status, True, evidence, request.track_id).validate(request)


def recovery_action(code, *, retryable=False):
    return asdict(ClientFailure(code, retryable=bool(retryable)).recovery)


class DesktopLauncherClient:
    def __init__(self, *, executable=None, save_path=None, backup_dir=None, profile_path=None,
                 submit_fn=None):
        import qbittorrent_submit as qb
        self.executable = executable
        self.save_path = Path(save_path) if save_path else qb.DEFAULT_SAVE_PATH
        self.backup_dir = Path(backup_dir) if backup_dir else qb.DEFAULT_BACKUP_DIR
        self.profile_path = Path(profile_path) if profile_path else None
        self.submit_fn = submit_fn or qb.submit_magnet

    def preflight(self):
        import qbittorrent_submit as qb
        try:
            executable = qb.find_executable(self.executable)
            details = qb.require_client_context(executable)
            return ClientContext('desktop-launcher', True, details)
        except qb.SubmissionError as exc:
            raise ClientFailure(exc.code, retryable=bool(exc.retryable), details=exc.diagnostics) from exc

    def inspect(self, info_hash):
        import qbittorrent_submit as qb
        try:
            evidence = qb._acceptance_evidence(info_hash, self.backup_dir)
            valid = evidence.get('fastresume_valid') is True and evidence.get('torrent_valid') is True
            return AcceptanceEvidence(info_hash, valid, evidence)
        except OSError as exc:
            raise ClientFailure('permission_denied') from exc

    def submit(self, request):
        import qbittorrent_submit as qb
        request.validate()
        self.preflight()
        if request.torrent_path:
            raise ClientFailure('desktop_torrent_file_not_supported')
        try:
            result = self.submit_fn(request.magnet, source_url=request.source_url,
                executable=self.executable, save_path=Path(request.save_path) if request.save_path else self.save_path,
                backup_dir=self.backup_dir, profile_path=self.profile_path)
            if result.get('status') not in SUCCESS_STATUSES or result.get('info_hash') != request.info_hash or result.get('ok') is not True:
                raise ClientFailure('handoff_unverified', details=result)
            ev = AcceptanceEvidence(request.info_hash, result['status'] in {'already_present','submitted_verified'}, result)
            return receipt(request, result['status'], ev)
        except qb.SubmissionError as exc:
            raise ClientFailure(exc.code, retryable=bool(exc.retryable), details=exc.diagnostics) from exc


class QbittorrentWebApiClient:
    def __init__(self, base_url='http://127.0.0.1:8080', *, username=None, password=None, timeout=8, opener=None):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('invalid_client_url')
        self.base_url = base_url.rstrip('/')
        self.username, self.password, self.timeout = username, password, timeout
        self.opener = opener or build_opener(HTTPCookieProcessor(CookieJar()))

    def _request(self, path, data=None, content_type=None):
        headers = {'Referer': self.base_url + '/'}
        if content_type:
            headers['Content-Type'] = content_type
        try:
            with self.opener.open(Request(self.base_url + path, data=data, headers=headers), timeout=self.timeout) as response:
                return response.read()
        except HTTPError as exc:
            code = 'authentication_failed' if exc.code in {401,403} else 'client_busy' if exc.code in {409,429,503} else 'client_http_error'
            raise ClientFailure(code, retryable=code == 'client_busy', details={'http_status': exc.code}) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ClientFailure('client_unavailable', retryable=True) from exc

    def preflight(self):
        if self.username is not None:
            result = self._request('/api/v2/auth/login', urlencode({'username':self.username,'password':self.password or ''}).encode(), 'application/x-www-form-urlencoded')
            if result.strip() != b'Ok.':
                raise ClientFailure('authentication_failed')
        version = self._request('/api/v2/app/version').decode('utf-8').strip()
        if not version.startswith('v'):
            raise ClientFailure('unexpected_client_response')
        return ClientContext('qbittorrent-webapi', True, {'version':version})

    def inspect(self, info_hash):
        try:
            rows = json.loads(self._request('/api/v2/torrents/info?' + urlencode({'hashes':info_hash})))
            if not isinstance(rows, list):
                raise ValueError('expected torrent array')
            exact = [r for r in rows if isinstance(r, dict) and r.get('hash','').lower() == info_hash]
            return AcceptanceEvidence(info_hash, bool(exact), {'torrent':exact[0] if exact else None})
        except (ValueError, TypeError) as exc:
            raise ClientFailure('invalid_client_response') from exc

    def submit(self, request):
        request.validate()
        self.preflight()
        existing = self.inspect(request.info_hash)
        if existing.verified:
            return receipt(request, 'already_present', existing)
        if request.torrent_path:
            boundary = 'watch-' + request.operation_id
            data = Path(request.torrent_path).read_bytes()
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="torrents"; filename="release.torrent"\r\nContent-Type: application/x-bittorrent\r\n\r\n'.encode() + data + b'\r\n')
            if request.save_path:
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="savepath"\r\n\r\n{request.save_path}\r\n'.encode()
            body += f'--{boundary}--\r\n'.encode()
            content_type = 'multipart/form-data; boundary=' + boundary
        else:
            fields = {'urls':request.magnet}
            if request.save_path:
                fields['savepath'] = request.save_path
            body = urlencode(fields).encode()
            content_type = 'application/x-www-form-urlencoded'
        result = self._request('/api/v2/torrents/add', body, content_type)
        if result.strip() != b'Ok.':
            raise ClientFailure('client_rejected')
        try:
            evidence = self.inspect(request.info_hash)
        except ClientFailure as exc:
            # The successful add response is already acceptance. A subsequent
            # inspection failure must not discard that pivot.
            evidence = AcceptanceEvidence(request.info_hash, False, {'add_response':'Ok.', 'inspection_error':asdict(exc.recovery)})
        return receipt(request, 'submitted_verified' if evidence.verified else 'submitted', evidence)
