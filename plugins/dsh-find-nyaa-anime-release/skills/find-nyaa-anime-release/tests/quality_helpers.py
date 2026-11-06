"""Test-only capability standing in for a successful validator."""
from submission_gate import _issue

def permit(info_hash, source_url=None):
    return _issue(info_hash, '1', source_url or 'https://nyaa.si/view/1',
                  {'tier':'browse'}, 'test-review', 'test-detail')
