"""Small authenticated Bangumi v0 client. Never expose credentials in reports."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from anime_release.storage import atomic_json

API = 'https://api.bgm.tv'
USER_AGENT = 'AnimeRelease/0.2 (https://github.com/divisioncassini05-lab/find-nyaa-anime-release)'
TOKEN_URL = 'https://next.bgm.tv/demo/access-token'


class BangumiError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def positive_id(value):
    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
        raise BangumiError('invalid_bangumi_id')
    return int(value)


def config_path(state):
    path = Path(state)
    return path.with_name(path.stem + '.bangumi.json')


def load_config(state):
    path = config_path(state)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, OSError):
        raise BangumiError('invalid_bangumi_config') from None
    if not isinstance(data, dict) or data.get('version') != 1 or type(data.get('account_id')) is not int or data['account_id'] <= 0 or not data.get('username'):
        raise BangumiError('invalid_bangumi_config')
    return data


def setup_hint():
    return {'setup_url': TOKEN_URL, 'message': 'Bangumi 为可选配置，不影响搜索。请在官方页面创建 Access Token，然后说“连接 Bangumi”，在本机小窗口填写；不要把令牌发到聊天里。无桌面环境仍可使用令牌文件或环境变量。',
            'next_action': 'python scripts/setup_gui.py --section bangumi'}


def credentials(config):
    if config.get('token_file'):
        try:
            token = Path(config['token_file']).read_text(encoding='utf-8-sig').strip()
        except OSError:
            raise BangumiError('bangumi_token_file_unavailable') from None
    else:
        token = os.environ.get(config.get('token_env', 'BANGUMI_ACCESS_TOKEN'), '').strip()
    if not token or any(c.isspace() for c in token):
        raise BangumiError('bangumi_token_required')
    return token


class BangumiClient:
    def __init__(self, token, *, timeout=8, opener=None):
        self._token = token
        self.timeout = timeout
        self._opener = opener or build_opener(NoRedirect())

    def request(self, method, path, payload=None):
        if not path.startswith('/v0/') or '://' in path:
            raise BangumiError('invalid_bangumi_endpoint')
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        req = Request(API + path, data=body, method=method, headers={
            'Authorization': 'Bearer ' + self._token, 'User-Agent': USER_AGENT,
            'Content-Type': 'application/json', 'Accept': 'application/json',
        })
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise BangumiError('bangumi_response_too_large')
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            raise BangumiError('bangumi_http_' + str(exc.code)) from None
        except (URLError, TimeoutError, OSError):
            raise BangumiError('bangumi_network_unavailable') from None
        except (ValueError, UnicodeError):
            raise BangumiError('bangumi_invalid_response') from None

    def me(self):
        return self.request('GET', '/v0/me')

    def pages(self, path, **query):
        items = []
        for offset in range(0, 10000, 100):
            page = self.request('GET', path + '?' + urlencode({**query, 'limit': 100, 'offset': offset}))
            if not isinstance(page, dict) or not isinstance(page.get('data'), list):
                raise BangumiError('bangumi_invalid_page')
            rows = page['data']
            items.extend(rows)
            if len(rows) < 100 or isinstance(page.get('total'), int) and len(items) >= page['total']:
                return items
        raise BangumiError('bangumi_pagination_incomplete')

    def watching(self, username):
        return self.collections(username, 3)

    def collections(self, username, collection_type=None):
        query = {'subject_type': 2}
        if collection_type is not None:
            if collection_type not in {1, 2, 3, 4, 5}:
                raise BangumiError('invalid_bangumi_collection')
            query['type'] = collection_type
        return self.pages('/v0/users/' + quote(username, safe='') + '/collections', **query)

    def collection(self, username, subject_id):
        return self.request('GET', '/v0/users/' + quote(username, safe='') + '/collections/' + str(positive_id(subject_id)))

    def subject(self, subject_id):
        return self.request('GET', '/v0/subjects/' + str(positive_id(subject_id)))

    def episodes(self, subject_id):
        return self.pages('/v0/users/-/collections/' + str(positive_id(subject_id)) + '/episodes', episode_type=0)

    def set_watched(self, subject_id, episode_ids):
        ids = list(dict.fromkeys(positive_id(value) for value in episode_ids))
        for start in range(0, len(ids), 100):
            self.request('PATCH', '/v0/users/-/collections/' + str(positive_id(subject_id)) + '/episodes',
                         {'episode_id': ids[start:start + 100], 'type': 2})

    def set_collection(self, subject_id, collection_type):
        if collection_type not in {2, 3}:
            raise BangumiError('invalid_collection_change')
        # Only this field changes: ratings, comments, privacy and tags stay intact.
        return self.request('POST', '/v0/users/-/collections/' + str(positive_id(subject_id)), {'type': collection_type})


def configured_client(config, *, factory=BangumiClient):
    client = factory(credentials(config))
    me = client.me()
    if str(me.get('id')) != str(config['account_id']):
        raise BangumiError('bangumi_account_changed_reconnect_required')
    return client


def connect(state, *, token_env='BANGUMI_ACCESS_TOKEN', token_file=None, factory=BangumiClient):
    config = {'version': 1, 'token_env': token_env, 'delivery_as_watched': True}
    if token_file:
        config['token_file'] = str(Path(token_file).expanduser().resolve(strict=True))
    client = factory(credentials(config))
    me = client.me()
    account = positive_id(me.get('id'))
    old = load_config(state)
    if old and str(old['account_id']) != str(account):
        raise BangumiError('bangumi_account_conflict_use_separate_state')
    config.update(account_id=account, username=me.get('username') or str(account))
    atomic_json(config_path(state), config)
    return {'status': 'bangumi_connected', 'account_id': account, 'username': config['username'],
            'delivery_as_watched': True, 'config_path': str(config_path(state))}
