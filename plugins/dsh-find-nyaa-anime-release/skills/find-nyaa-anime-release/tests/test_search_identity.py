import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from search_identity import subject_evidence


class Source:
    def __init__(self, subject):
        self.subject = subject
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return io.BytesIO(json.dumps(self.subject).encode())


def test_identity_is_one_public_bounded_read_not_an_approved_scope():
    source = Source({'id': 123, 'name': 'Part Four', 'name_cn': '第四季', 'eps': 11,
                     'platform': 'TV', 'summary': 'Long plot must not be repeated',
                     'rating': {'score': 9}, 'infobox': [{'key': '别名', 'value': ['Full Alias']},
                        {'key': '放送结束', 'value': '2026-06-17'}, {'key': '导演', 'value': 'Unneeded'}]})
    result = subject_evidence(123, opener=source)
    assert result['subject']['eps'] == 11 and result['subject']['name_cn'] == '第四季'
    assert len(result['infobox']) == 2 and 'reviewed' not in result
    assert 'Long plot' not in json.dumps(result) and 'rating' not in result['subject']
    request, timeout = source.calls[0]
    assert len(source.calls) == 1 and timeout == 8
    assert request.full_url == 'https://api.bgm.tv/v0/subjects/123'
    assert not request.has_header('Authorization')


def test_bad_identity_response_requires_independent_evidence():
    result = subject_evidence(123, opener=Source({'id': 999, 'eps': 11}))
    assert result['status'] == 'identity_evidence_unavailable'
    assert 'subject' not in result
