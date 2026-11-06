"""Uniform stage errors for read-only metadata queries. TLS is never weakened."""
import json
import time
import urllib.error
import urllib.request
from http_transport import error_code
from .models import WorkflowError

class MetadataTransportError(urllib.error.URLError):
    def __init__(self, detail):
        self.detail = detail
        super().__init__(json.dumps(detail.as_dict(), ensure_ascii=False))

def request_json(request, timeout):
    # These endpoints use POST for read-only GraphQL/search, never delivery.
    deadline = time.monotonic() + timeout
    attempts = []
    for attempt in range(2):
        try:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            with urllib.request.urlopen(request, timeout=remaining/(2-attempt)) as response:
                body = response.read(8*1024*1024+1)
            if len(body)>8*1024*1024:
                raise ValueError('response_too_large')
            return json.loads(body.decode('utf-8'))
        except urllib.error.HTTPError as exc:
            # Preserve 404 semantics for official AiringSchedule fallback.
            if exc.code == 404:
                raise
            code = error_code(exc)
            exc.close()
        except (OSError, ValueError, UnicodeError) as exc:
            code = error_code(exc) if isinstance(exc,OSError) else 'invalid_provider_response'
        attempts.append({'attempt':attempt+1,'code':code})
        retryable = code in {'timeout','connection_failed','dns_failed','http_502','http_503','http_504'}
        if not retryable:
            break
    action = ('inspect_tls_trust_and_execution_context' if code.startswith('tls_') else
              'request_approved_execution_context' if code=='permission_denied' else 'inspect_provider_transport')
    raise MetadataTransportError(WorkflowError('metadata',code,retryable,tuple(attempts),action))
