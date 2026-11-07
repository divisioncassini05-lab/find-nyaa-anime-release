"""Optional Bangumi library mirror. Never participates in release decisions."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import uuid
import unicodedata

from anime_release.storage import atomic_json
from .bangumi_client import BangumiError, configured_client, load_config, positive_id
from .store import now_iso, require

TTL_SECONDS = 60
COLLECTION_TYPES = {'wish': 1, 'completed': 2, 'watching': 3, 'on_hold': 4, 'dropped': 5, 'all': None}


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value or '').casefold() if c.isalnum())


def collection_item(row):
    subject = row.get('subject') or {}
    return {'subject_id': positive_id(row.get('subject_id', subject.get('id'))),
            'title': subject.get('name_cn') or subject.get('name'),
            'original_title': subject.get('name'), 'collection_type': row.get('type'),
            'watched_count': row.get('ep_status', 0), 'episode_count': subject.get('eps'),
            'rating': row.get('rate') or None, 'comment': row.get('comment') or '',
            'tags': row.get('tags') or [], 'private': bool(row.get('private'))}


def fresh(timestamp):
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds()
        return 0 <= age < TTL_SECONDS
    except (TypeError, ValueError):
        return False


def episode_snapshot(rows, offset=0):
    mapping, watched = {}, []
    for row in rows:
        ep = row.get('episode') or {}
        if ep.get('type') != 0:
            continue
        try:
            number = Decimal(str(ep.get('sort')))
        except InvalidOperation:
            continue
        if not number.is_finite() or number != number.to_integral_value():
            continue
        local = int(number) - offset
        if local <= 0:
            continue
        key = str(local)
        if key in mapping:
            raise BangumiError('bangumi_duplicate_episode_number')
        mapping[key] = positive_id(ep.get('id'))
        if row.get('type') == 2:
            watched.append(local)
    if mapping and '1' not in mapping:
        raise BangumiError('bangumi_numbering_confirmation_required')
    return mapping, sorted(watched)


def watched_scope(binding, *, episode=None, through=None, complete=False):
    mapping = binding['episode_map']
    if complete:
        count = binding.get('episode_count')
        if not count or set(mapping) != {str(n) for n in range(1, count + 1)}:
            raise BangumiError('bangumi_complete_scope_unconfirmed')
        numbers = list(range(1, count + 1))
    elif through is not None:
        if not 0 < through <= 10000:
            raise BangumiError('invalid_watched_episodes')
        numbers = list(range(1, through + 1))
    else:
        numbers = [positive_id(episode)]
    if any(str(n) not in mapping for n in numbers):
        raise BangumiError('bangumi_episode_mapping_incomplete')
    return numbers


class BangumiSync:
    def __init__(self, repo, config=None, client=None):
        self.repo = repo
        self.config = config if config is not None else load_config(repo.path)
        if not self.config:
            raise BangumiError('bangumi_not_connected')
        self._client = client
        self._subjects = {}

    @property
    def client(self):
        if self._client is None:
            self._client = configured_client(self.config)
        return self._client

    def watching(self, *, refresh=False):
        return self.collections(refresh=refresh)

    def collections(self, *, collection='watching', query=None, min_rating=0,
                    comments_only=False, limit=30, offset=0, refresh=False):
        if collection not in COLLECTION_TYPES or not 1 <= limit <= 100 or offset < 0 or not 0 <= min_rating <= 10:
            raise BangumiError('invalid_bangumi_list_filter')
        cache = self.repo.path.with_name(self.repo.path.stem + '.bangumi-list-cache.json')
        data = None
        if cache.exists() and not refresh:
            try:
                saved = json.loads(cache.read_text(encoding='utf-8'))
                if (saved.get('account_id') == self.config['account_id'] and saved.get('collection') == collection
                        and fresh(saved.get('checked_at'))):
                    data = saved
            except (ValueError, OSError):
                pass
        cached = data is not None
        if data is None:
            kind = COLLECTION_TYPES[collection]
            rows = self.client.collections(self.config['username'], kind)
            items = [collection_item(row) for row in rows
                     if row.get('subject_type', (row.get('subject') or {}).get('type')) == 2
                     and (kind is None or row.get('type') == kind)]
            data = {'account_id': self.config['account_id'], 'collection': collection,
                    'checked_at': now_iso(), 'items': items}
            atomic_json(cache, data)
        items = data['items']
        query = normalized(query)
        filtered = [item for item in items if (item.get('rating') or 0) >= min_rating
                    and (not comments_only or item.get('comment'))
                    and (not query or query in normalized(' '.join(str(item.get(k) or '') for k in ('title', 'original_title', 'comment', 'tags'))))]
        selected = [{**item, 'comment': item['comment'][:1000], 'comment_truncated': len(item['comment']) > 1000}
                    for item in filtered[offset:offset + limit]]
        return {'status': 'bangumi_watching' if collection == 'watching' else 'bangumi_library',
                'account_id': data['account_id'], 'collection': collection, 'checked_at': data['checked_at'],
                'cached': cached, 'library_count': len(items), 'matched_count': len(filtered),
                'offset': offset, 'next_offset': offset + limit if offset + limit < len(filtered) else None,
                'items': selected}

    def progress(self, subject_id, *, episode_offset=0):
        binding = {'account_id': self.config['account_id'], 'subject_id': positive_id(subject_id),
                   'episode_offset': episode_offset}
        snapshot = self.snapshot(binding)
        collection = collection_item(self.client.collection(self.config['username'], binding['subject_id']))
        return {'status': 'bangumi_progress', **collection,
                **{k: snapshot[k] for k in ('subject_id', 'collection_type', 'watched_episodes', 'episode_count', 'synced_at')},
                'episode_offset': episode_offset}

    def _binding(self, track_id):
        show = self.repo.find(track_id=track_id)
        require(show is not None, 'track_not_found')
        binding = show.get('bangumi')
        if not binding:
            raise BangumiError('bangumi_binding_required')
        if binding['account_id'] != self.config['account_id']:
            raise BangumiError('bangumi_account_conflict')
        return show, binding

    def snapshot(self, binding, *, subject=None):
        sid = binding['subject_id']
        collection = self.client.collection(self.config['username'], sid)
        subject = subject or self._subjects.get(sid) or self.client.subject(sid)
        self._subjects[sid] = subject
        if subject.get('type') != 2 or int(subject.get('id', sid)) != sid:
            raise BangumiError('bangumi_not_anime')
        mapping, watched = episode_snapshot(self.client.episodes(sid), binding['episode_offset'])
        count = subject.get('eps')
        if type(count) is not int or count <= 0:
            count = None
        if count and any(int(n) > count for n in mapping):
            raise BangumiError('bangumi_episode_scope_conflict')
        return {**binding, 'collection_type': collection['type'], 'episode_count': count,
                'episode_map': mapping, 'watched_episodes': watched, 'synced_at': now_iso()}

    def bind(self, track_id, subject_id, *, episode_offset=0, add_watching=False):
        sid = positive_id(subject_id)
        show = self.repo.find(track_id=track_id)
        require(show is not None, 'track_not_found')
        existing = show['identity'].get('provider_bindings', {}).get('bangumi')
        if existing and str(existing['entry_id']) != str(sid):
            raise BangumiError('bangumi_identity_conflict')
        for other in self.repo.read()['shows']:
            if other['track_id'] != track_id and other.get('bangumi', {}).get('subject_id') == sid:
                raise BangumiError('bangumi_subject_already_bound')
        subject = self.client.subject(sid)
        if subject.get('type') != 2:
            raise BangumiError('bangumi_not_anime')
        binding = {'account_id': self.config['account_id'], 'subject_id': sid,
                   'episode_offset': episode_offset}
        try:
            snapshot = self.snapshot(binding, subject=subject)
        except BangumiError as exc:
            if str(exc) != 'bangumi_http_404' or not add_watching:
                raise
            self.client.set_collection(sid, 3)
            snapshot = self.snapshot(binding, subject=subject)
        self.repo.command(track_id, 'bind_bangumi', expected_revision=show['revision'], binding=snapshot)
        return self.track_report(track_id)

    def refresh_track(self, track_id, *, refresh=False):
        with self.repo.work_lock(track_id):
            show, binding = self._binding(track_id)
            if not refresh and fresh(binding.get('synced_at')):
                return {**self.track_report(track_id), 'cached': True}
            snapshot = self.snapshot(binding)
            self.repo.command(track_id, 'record_bangumi_snapshot', expected_revision=show['revision'], snapshot=snapshot)
            return {**self.track_report(track_id), 'cached': False}

    def track_report(self, track_id):
        show, binding = self._binding(track_id)
        return {'status': 'bangumi_synced', 'track_id': track_id, 'subject_id': binding['subject_id'],
                'title': show['identity']['title'], 'collection_type': binding.get('collection_type'),
                'watched_episodes': binding.get('watched_episodes', []), 'episode_count': binding.get('episode_count'),
                'next_episode': show['progress']['target_episode'], 'synced_at': binding.get('synced_at'),
                'pending_writes': sum(a['kind'] == 'bangumi_watched' and a['status'] != 'done' for a in show['outbox'])}

    def watched(self, track_id, *, episode=None, through=None, complete=False):
        self.refresh_track(track_id, refresh=True)
        show, binding = self._binding(track_id)
        numbers = watched_scope(binding, episode=episode, through=through, complete=complete)
        event_id = 'user:' + uuid.uuid4().hex
        self.repo.command(track_id, 'queue_bangumi_watch', episodes=numbers, complete=complete,
                          explicit=True, event_id=event_id)
        from .outbox import drain
        actions = drain(self.repo, track_id=track_id, bangumi=self, kinds={'bangumi_watched'})
        return {**self.track_report(track_id), 'actions': actions,
                'status': 'bangumi_sync_pending' if self.track_report(track_id)['pending_writes'] else 'bangumi_watched'}

    def watched_subject(self, subject_id, *, episode_offset=0, episode=None, through=None, complete=False):
        sid = positive_id(subject_id)
        # No synthetic local tracking entry for an old series or movie.
        binding = {'account_id': self.config['account_id'], 'subject_id': sid, 'episode_offset': episode_offset}
        before = self.snapshot(binding)
        numbers = watched_scope(before, episode=episode, through=through, complete=complete)
        after = self._write_watched(before, numbers, complete=complete)
        return {'status': 'bangumi_watched', 'subject_id': sid, 'collection_type': after['collection_type'],
                'watched_episodes': after['watched_episodes'], 'local_progress_changed': False}

    def apply_action(self, track_id, action):
        with self.repo.work_lock(track_id):
            return self._apply_action(track_id, action)

    def _apply_action(self, track_id, action):
        show, binding = self._binding(track_id)
        payload = action['payload']
        if any(payload[k] != binding[k] for k in ('account_id', 'subject_id', 'episode_offset')) or payload['identity_revision'] != show['identity_revision']:
            raise BangumiError('bangumi_action_identity_conflict')
        try:
            before = self.snapshot(binding)
        except BangumiError as exc:
            if str(exc) != 'bangumi_http_404' or payload['source'] != 'delivery':
                raise
            # A verified delivery can start the personal collection, never vice versa.
            subject = self.client.subject(binding['subject_id'])
            if subject.get('type') != 2:
                raise BangumiError('bangumi_not_anime')
            self.client.set_collection(binding['subject_id'], 3)
            before = self.snapshot(binding, subject=subject)
        after = self._write_watched(before, payload['episodes'], complete=payload.get('complete', False))
        self.repo.command(track_id, 'record_bangumi_snapshot', snapshot=after)
        return {'status': 'bangumi_verified', 'subject_id': binding['subject_id'],
                'account_id': binding['account_id'], 'episodes': payload['episodes'],
                'collection_type': after['collection_type'], 'checked_at': now_iso()}

    def _write_watched(self, before, episodes, *, complete=False):
        mapping = before['episode_map']
        if any(str(n) not in mapping for n in episodes):
            raise BangumiError('bangumi_episode_mapping_incomplete')
        needed = [n for n in episodes if n not in before['watched_episodes']]
        if needed:
            self.client.set_watched(before['subject_id'], [mapping[str(n)] for n in needed])
        after = self.snapshot(before)
        if not set(episodes) <= set(after['watched_episodes']):
            raise BangumiError('bangumi_write_not_confirmed')
        count = after['episode_count']
        fully_watched = bool(count) and set(range(1, count + 1)) <= set(after['watched_episodes'])
        if complete and not fully_watched:
            raise BangumiError('bangumi_complete_scope_unconfirmed')
        if (complete or fully_watched) and after['collection_type'] != 2:
            self.client.set_collection(before['subject_id'], 2)
            after = self.snapshot(before)
            if after['collection_type'] != 2:
                raise BangumiError('bangumi_write_not_confirmed')
        cache = self.repo.path.with_name(self.repo.path.stem + '.bangumi-list-cache.json')
        # An acknowledged write invalidates the compact list, never the delivery.
        try:
            cache.unlink(missing_ok=True)
        except OSError:
            pass
        return after


