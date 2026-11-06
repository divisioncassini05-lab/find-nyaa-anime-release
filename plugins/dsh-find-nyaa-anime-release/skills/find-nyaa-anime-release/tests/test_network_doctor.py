from unittest.mock import Mock, patch, MagicMock
import ssl
import urllib.error

import network_doctor as doctor
from http_transport import TransportError
from nyaa_client import NyaaNetworkError


def test_credentials_are_never_reported():
    with patch.object(doctor, 'proxy_for', return_value='http://user:SECRET@localhost:7897'):
        assert doctor.proxy_summary() == {
            'configured': True, 'scheme': 'http', 'host': 'localhost', 'port': 7897}


def test_dead_proxy_stops_before_request():
    client = Mock()
    with patch.object(doctor, 'proxy_for', return_value='http://localhost:7897'):
        result = doctor.diagnose(client=client, connect=Mock(side_effect=ConnectionRefusedError()))
    assert result['status'] == 'proxy_unreachable'
    client.fetch_listing.assert_not_called()


def test_http_success_requires_real_listing():
    client = Mock()
    client.fetch_listing.return_value = '<html>challenge-platform</html>'
    with patch.object(doctor, 'proxy_for', return_value=''):
        result = doctor.diagnose(client=client)
        assert result['status'] == 'unexpected_page' and result['challenge_marker']
        client.fetch_listing.return_value = '<title>Nyaa</title><table class="torrent-list">'
        assert doctor.diagnose(client=client)['status'] == 'nyaa_listing_reachable'


def test_tls_failure_is_not_reported_as_resource_absence():
    error = NyaaNetworkError('SECRET', url='https://nyaa.si/')
    error.__cause__ = TransportError('tls_handshake_failed',
        [{'backend': 'urllib', 'code': 'tls_unexpected_eof'}], 'nyaa.si')
    client = Mock(); client.fetch_listing.side_effect = error
    with patch.object(doctor, 'proxy_for', return_value=''):
        result = doctor.diagnose(client=client)
    assert result['scheduled_outcome'] == 'network_transient'
    assert result['status'] == 'request_failed'
    assert 'SECRET' not in str(result)
