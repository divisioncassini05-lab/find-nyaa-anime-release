"""Fault injection for TLS recovery: never weaken trust or repeat a submission."""
import io
import socket
import ssl
import subprocess
import urllib.error
import urllib.request
from unittest.mock import Mock, patch

import pytest

import http_transport as transport
from nyaa_client import NyaaClient, NyaaNotFoundError
import qbittorrent_submit as qbt


class Response(io.BytesIO):
    headers = {}


def request():
    return urllib.request.Request('https://nyaa.si/view/2165232')


@pytest.mark.parametrize('failure', [
    ssl.SSLEOFError(8, 'EOF'), socket.timeout('slow'), ConnectionResetError('reset'),
    socket.gaierror('dns'),
])
def test_transient_get_recovers_once(failure, capsys):
    opener = Mock(side_effect=[urllib.error.URLError(failure), Response(b'ok')])
    with patch.object(transport.time, 'sleep'):
        assert transport.fetch_bytes(request(), timeout=2, opener=opener, native_fallback=False) == (b'ok', None)
    assert opener.call_count == 2
    assert 'transport_recovery' in capsys.readouterr().err


def test_certificate_error_uses_independent_verified_backend_without_same_backend_retry(capsys):
    opener = Mock(side_effect=urllib.error.URLError(ssl.SSLCertVerificationError(1, 'untrusted')))
    with patch.object(transport, 'native_curl_path', return_value='curl.exe'), \
         patch.object(transport, 'native_get', return_value=(b'verified', None)) as native:
        assert transport.fetch_bytes(request(), timeout=2, opener=opener) == (b'verified', None)
    assert opener.call_count == 1 and native.call_count == 1
    assert 'tls_verification' in capsys.readouterr().err


def test_untrusted_certificate_fails_closed_on_both_backends():
    opener = Mock(side_effect=urllib.error.URLError(ssl.SSLCertVerificationError(1, 'untrusted')))
    with patch.object(transport, 'native_curl_path', return_value='curl.exe'), \
         patch.object(transport, 'native_get', side_effect=transport.TransportError('tls_certificate_verification_failed', [], 'nyaa.si')) as native:
        with pytest.raises(transport.TransportError) as failure:
            transport.fetch_bytes(request(), timeout=2, opener=opener)
    assert failure.value.code == 'tls_certificate_verification_failed'
    assert len(failure.value.attempts) == 2
    assert opener.call_count == native.call_count == 1


def test_retry_budget_exhaustion_does_not_start_another_backend():
    opener = Mock(side_effect=socket.timeout())
    with patch.object(transport.time, 'monotonic', side_effect=[0, 0, 3, 3, 3]), \
         patch.object(transport.time, 'sleep'), \
         patch.object(transport, 'native_curl_path', return_value='curl.exe'), \
         patch.object(transport, 'native_get') as native:
        with pytest.raises(transport.TransportError):
            transport.fetch_bytes(request(), timeout=2, opener=opener)
    assert opener.call_count == 1
    native.assert_not_called()


@pytest.mark.parametrize('code', [403, 404, 407, 429])
def test_permanent_http_errors_are_not_retried_or_rerouted(code):
    opener = Mock(side_effect=urllib.error.HTTPError(request().full_url, code, 'denied', {}, None))
    with patch.object(transport, 'native_get') as native:
        with pytest.raises(urllib.error.HTTPError):
            transport.fetch_bytes(request(), timeout=2, opener=opener)
    assert opener.call_count == 1
    native.assert_not_called()


def test_503_is_retried_once():
    opener = Mock(side_effect=[urllib.error.HTTPError(request().full_url, 503, 'busy', {}, None), Response(b'ok')])
    with patch.object(transport.time, 'sleep'):
        assert transport.fetch_bytes(request(), timeout=2, opener=opener, native_fallback=False)[0] == b'ok'
    assert opener.call_count == 2


def test_permission_failure_never_uses_fallback():
    with patch.object(transport, 'native_get') as native:
        with pytest.raises(transport.TransportError) as failure:
            transport.fetch_bytes(request(), timeout=2, opener=Mock(side_effect=PermissionError('denied')))
    assert failure.value.code == 'permission_denied'
    native.assert_not_called()


def test_native_command_keeps_verification_and_same_proxy():
    result = subprocess.CompletedProcess([], 0, stdout=b'ok', stderr=b'')
    with patch.object(transport, 'proxy_for', return_value='http://127.0.0.1:7897'), \
         patch.object(transport.subprocess, 'run', return_value=result) as run:
        assert transport.native_get(request(), 4, 2048, 'curl.exe') == (b'ok', None)
    args = run.call_args.args[0]
    assert args[1] == '--disable'  # Ignore .curlrc, including any insecure defaults.
    assert not any(arg in args for arg in ('-k', '--insecure', '--proxy-insecure', '--ssl-no-revoke'))
    assert args[args.index('--proxy') + 1] == 'http://127.0.0.1:7897'
    assert args[args.index('--proto-redir') + 1] == '=https'
    assert run.call_args.kwargs['timeout'] == 4


def test_native_error_does_not_leak_proxy_passwords():
    result = subprocess.CompletedProcess([], 60, stdout=b'', stderr=b'https://user:SECRET@proxy')
    with patch.object(transport, 'proxy_for', return_value=''), \
         patch.object(transport.subprocess, 'run', return_value=result):
        with pytest.raises(transport.TransportError) as failure:
            transport.native_get(request(), 4, 2048, 'curl.exe')
    assert 'SECRET' not in str(failure.value)
    assert failure.value.code == 'tls_certificate_verification_failed'


def test_windows_credential_failure_is_a_context_problem():
    result = subprocess.CompletedProcess([], 35, stdout=b'', stderr=b'SEC_E_NO_CREDENTIALS (0x8009030e) https://u:SECRET@proxy')
    with patch.object(transport, 'proxy_for', return_value=''), \
         patch.object(transport.subprocess, 'run', return_value=result):
        with pytest.raises(transport.TransportError) as failure:
            transport.native_get(request(), 4, 2048, 'curl.exe')
    assert failure.value.code == 'tls_user_context_unavailable'
    assert 'SEC_E_NO_CREDENTIALS' in str(failure.value) and 'SECRET' not in str(failure.value)


def test_exhausted_transients_attempt_only_two_python_and_one_native_get():
    opener = Mock(side_effect=socket.timeout())
    with patch.object(transport.time, 'sleep'), \
         patch.object(transport, 'native_curl_path', return_value='curl.exe'), \
         patch.object(transport, 'native_get', side_effect=transport.TransportError('timeout', [], 'nyaa.si')) as native:
        with pytest.raises(transport.TransportError) as failure:
            transport.fetch_bytes(request(), timeout=2, opener=opener)
    assert opener.call_count == 2 and native.call_count == 1
    assert len(failure.value.attempts) == 3


@pytest.mark.parametrize('name', transport._CA_OVERRIDES)
def test_explicit_trust_configuration_never_gets_bypassed(name):
    with patch.dict(transport.os.environ, {name: 'configured-ca-file'}):
        assert transport.native_curl_path() is None


def test_proxy_bypass_and_registry_selection_are_preserved():
    with patch.object(transport.urllib.request, 'proxy_bypass', return_value=False), \
         patch.object(transport.urllib.request, 'getproxies', return_value={'https': 'http://configured:1234', 'all': 'http://different:9'}):
        assert transport.proxy_for(request().full_url) == 'http://configured:1234'
    with patch.object(transport.urllib.request, 'proxy_bypass', return_value=True):
        assert transport.proxy_for(request().full_url) == ''


def test_get_only_and_response_size_limit():
    with pytest.raises(ValueError):
        transport.fetch_bytes(urllib.request.Request(request().full_url, data=b'body'), timeout=2)
    with pytest.raises(transport.TransportError) as failure:
        transport.fetch_bytes(request(), timeout=2, max_bytes=2, opener=Mock(return_value=Response(b'long')))
    assert failure.value.code == 'response_too_large'


def test_torrent_retry_keeps_hash_check_and_does_not_launch_client():
    opener = Mock(side_effect=[urllib.error.URLError(ssl.SSLEOFError(8, 'EOF')), Response(b'd4:infod6:lengthi1e4:name1:xee')])
    with patch.object(qbt, 'urlopen', opener), patch.object(transport.time, 'sleep'), \
         patch.object(qbt.subprocess, 'Popen') as launch:
        with pytest.raises(qbt.SubmissionError, match='does not match'):
            qbt.download_torrent('https://nyaa.si/download/2165232.torrent', expected_info_hash='0' * 40)
    assert opener.call_count == 2
    launch.assert_not_called()


def test_adapter_preserves_404():
    opener = Mock(side_effect=urllib.error.HTTPError(request().full_url, 404, 'gone', {}, None))
    with pytest.raises(NyaaNotFoundError):
        NyaaClient(opener=opener).get('2165232')
    assert opener.call_count == 1
