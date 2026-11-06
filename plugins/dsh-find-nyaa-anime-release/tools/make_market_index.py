#!/usr/bin/env python3
"""Create a format-1 index only after the publisher supplies a real source commit."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def make_index(repository, commit, subpath='', published_at=None):
    url = urlsplit(repository)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('A public HTTPS repository URL without credentials is required')
    if not re.fullmatch(r'[0-9a-fA-F]{40}', commit) or len(set(commit.lower())) == 1:
        raise ValueError('Supply the actual 40-hex commit containing this plugin')
    if subpath and (subpath.startswith('/') or '\\' in subpath or any(p in {'', '.', '..'} for p in subpath.split('/'))):
        raise ValueError('Plugin subpath must stay within the repository')
    package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
    locales = {language: json.loads((ROOT / 'locale' / (language + '.json')).read_text(encoding='utf-8'))['meta']
               for language in ('en', 'zh')}
    titles = {language: meta['title'] for language, meta in locales.items()}
    descriptions = {language: meta['description'] for language, meta in locales.items()}
    source = {'type': 'git', 'url': repository, 'commit': commit.lower()}
    if subpath:
        source['path'] = subpath
    return {'format': 1, 'title': titles,
            'plugins': [{'name': package['name'],
                         'title': titles,
                         'description': descriptions, 'author': package['author'],
                         'homepage': package.get('homepage', repository),
                         'repository': {'url': repository, **({'directory': subpath} if subpath else {})},
                         'icon': 'data:image/svg+xml;base64,' + base64.b64encode((ROOT / 'icon.svg').read_bytes()).decode(),
                         'versions': [{'version': package['version'],
                                       'publishTimestamp': published_at or int(datetime.now(timezone.utc).timestamp()),
                                       'source': source, 'engines': {'dsh': package['engines']['dsh']}}]}]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--path', default='')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(make_index(args.repository, args.commit, args.path), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Index generated. Confirm the source commit is public before publishing it.')
