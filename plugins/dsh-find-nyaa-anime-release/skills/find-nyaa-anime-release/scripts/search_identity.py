"""One public subject read, reduced to identity evidence for the Agent to judge."""
import json
from urllib.request import Request, build_opener

from watch_v3.bangumi_client import API, USER_AGENT, NoRedirect, positive_id


def subject_evidence(subject_id, *, opener=None):
    subject_id = positive_id(subject_id)
    url = f'{API}/v0/subjects/{subject_id}'
    try:
        request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
        with (opener or build_opener(NoRedirect())).open(request, timeout=8) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError('subject_too_large')
        subject = json.loads(data)
        if not isinstance(subject, dict) or subject.get('id') != subject_id:
            raise ValueError('subject_mismatch')
        keys = {'别名', '中文名', '话数', '集数', '放送开始', '放送结束', '上映年度', '上映日期', '官方网站'}
        return {'status': 'identity_evidence', 'source_url': url,
                'subject': {key: subject.get(key) for key in
                            ('id', 'name', 'name_cn', 'type', 'platform', 'date', 'eps', 'total_episodes')},
                'infobox': [item for item in subject.get('infobox', [])
                            if isinstance(item, dict) and item.get('key') in keys],
                'next': 'AI must verify the requested work/part, kind, count and release aliases. '
                        'These source fields do not approve a scope or prove completion.'}
    except (OSError, ValueError, TypeError):
        return {'status': 'identity_evidence_unavailable', 'source_url': url,
                'next': 'Use a bounded independent identity source; do not dump personal state or retry setup.'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bangumi_id', type=int)
    args = parser.parse_args()
    print(json.dumps(subject_evidence(args.bangumi_id), ensure_ascii=False, separators=(',', ':')))
