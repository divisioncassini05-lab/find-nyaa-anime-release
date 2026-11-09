"""Native panel ownership and its manual cloud-write policy."""
import json
from pathlib import Path


def owns_track(state_path, track_id):
    path = Path(state_path).with_suffix('.plans.json')
    if not path.exists():
        return False
    raw = path.read_text(encoding='utf-8-sig')
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('invalid_panel_plans')
    data = json.loads(raw)
    if data.get('version') != 1 or not isinstance(data.get('plans'), list):
        raise ValueError('invalid_panel_plans')
    return any(p.get('trackId') == track_id for p in data['plans'])


def retain_tracks(state_path, track_ids):
    return any(owns_track(state_path, track_id) for track_id in track_ids)
