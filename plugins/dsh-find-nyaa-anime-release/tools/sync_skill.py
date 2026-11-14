#!/usr/bin/env python3
"""Rebuild a self-contained DSH skill from a local upstream checkout."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'__pycache__', '.pytest_cache', '.hypothesis', '.git'}
PRIVATE_SUFFIXES = ('.bangumi.json', '.bangumi-list-cache.json')
TOP = {'SKILL.md', 'pytest.ini', 'requirements-parsers.txt', 'requirements-search.txt'}
DIRECTORIES = {'scripts', 'references', 'data', 'tests'}


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Upstream contract changed; review this adapter before rebuilding: ' + old[:80])
    return text.replace(old, new)


def rebuild(source, output_root=None, *, emit=True):
    source = Path(source).resolve()
    output_root = Path(output_root).resolve() if output_root else ROOT
    target = output_root / 'skills' / 'find-nyaa-anime-release'
    if source == target.resolve() or target.resolve() in source.parents:
        raise ValueError('Source must be an independent skill directory')
    if not (source / 'SKILL.md').is_file():
        raise ValueError('Source has no SKILL.md')
    files = []
    def visit(directory):
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            if path.is_symlink() or path.name in EXCLUDED or path.name.endswith(PRIVATE_SUFFIXES):
                continue
            relative = path.relative_to(source)
            if len(relative.parts) == 1 and path.name not in TOP | DIRECTORIES:
                continue
            if path.is_dir():
                yield from visit(path)
            elif path.suffix not in {'.pyc', '.pyo'}:
                yield path
    for path in visit(source):
        relative = path.relative_to(source)
        content = path.read_bytes()
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        files.append({'path': relative.as_posix(), 'sha256': hashlib.sha256(content).hexdigest()})
    files.sort(key=lambda item: item['path'])

    def edit(relative, transform):
        path = target / relative
        path.write_text(transform(path.read_text(encoding='utf-8-sig')), encoding='utf-8', newline='\n')

    edit('scripts/qbittorrent_submit.py', lambda text: replace_once(text,
        'DEFAULT_SAVE_PATH = Path(r"C:\\User_data\\Download\\qBittorrent")\nDEFAULT_BACKUP_DIR = (\n'
        '    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))\n'
        '    / "qBittorrent"\n    / "BT_backup"\n)',
        'from dsh_paths import download_directory, qb_backup_directory\n\n'
        'DEFAULT_SAVE_PATH = download_directory()\nDEFAULT_BACKUP_DIR = qb_backup_directory()'))
    edit('scripts/watch_v3/automation.py', lambda text: replace_once(text,
        "    base = Path(directory) if directory is not None else Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'automations'",
        "    if directory is None:\n        from dsh_host import inventory_for_state\n        return inventory_for_state(data)\n    base = Path(directory)"))
    for relative in ('scripts/watch_v3/outbox.py', 'scripts/watch_v3/finalization.py'):
        edit(relative, lambda text: text.replace("'automation_update'", "'schedule_edit'"))
    edit('scripts/watch_v3/store.py', lambda text: replace_once(text,
        'def _delivery_mirror(state_path, show):\n',
        'def _delivery_mirror(state_path, show):\n'
        '    from dsh_panel_policy import owns_track\n'
        "    if owns_track(state_path, show['track_id']):\n        return False\n"))
    edit('scripts/watch_v3/outbox.py', lambda text: replace_once(text,
        "                elif item['kind'] == 'bangumi_watched':\n",
        "                elif item['kind'] == 'bangumi_watched':\n"
        '                    from dsh_panel_policy import owns_track\n'
        "                    if item.get('payload', {}).get('source') == 'delivery' and owns_track(repo.path, tid):\n"
        "                        results.append({'track_id': tid, 'outbox_id': item['outbox_id'], 'status': 'manual_sync_required'})\n"
        '                        continue\n'))
    edit('scripts/watch_v3/finalization.py', lambda text: replace_once(text,
        "    preview = _preview(data, track_id, repo.automation_inventory(data))\n",
        "    preview = _preview(data, track_id, repo.automation_inventory(data))\n"
        '    from dsh_panel_policy import retain_tracks\n'
        "    if apply and retain_tracks(repo.path, preview.get('target_track_ids', [track_id])):\n"
        "        return {**preview, 'status': 'panel_record_retained', 'deleted_track_ids': []}\n"))
    edit('scripts/watch_v3/outbox.py', lambda text: replace_once(text,
        "                elif item['kind'] == 'delete_owning_automation':\n",
        "                elif item['kind'] == 'delete_owning_automation':\n"
        '                    from dsh_panel_policy import retain_tracks\n'
        "                    if retain_tracks(repo.path, item.get('payload', {}).get('target_track_ids', [tid])):\n"
        "                        results.append({'track_id': tid, 'outbox_id': item['outbox_id'], 'status': 'panel_record_retained'})\n"
        '                        continue\n'))
    edit('scripts/scheduled_watch.py', lambda text: text.replace('Agent calls automation_update', 'Agent calls schedule_edit'))
    edit('scripts/watch_v3/cli.py', lambda text: replace_once(text,
        "q.add_argument('--qbittorrent-save-path', type=Path)",
        "q.add_argument('--qbittorrent-save-path', help='Client-side path; kept verbatim for remote Web API')"))
    edit('scripts/watch_v3/evidence.py', lambda text: replace_once(text,
        '        return SelectionResult(release, report)\n',
        '        from dsh_panel_run import record_found\n'
        '        record_found(report, show=show, review=manifest.content, review_path=manifest.path)\n'
        '        return SelectionResult(release, report)\n'))
    edit('scripts/watch_v3/workflow.py', lambda text: replace_once(text,
        '            if not plan.deliverable:\n',
        '            from dsh_panel_targets import allows_backfill\n'
        "            if plan.phase != 'blocked' and manifest.content.get('intent') == 'specific_episode' and allows_backfill(self.repo.path, tid):\n"
        '                plan = TargetPlan(manifest.content["target_episode"], plan.phase, True)\n'
        '            if not plan.deliverable:\n'))
    edit('scripts/watch_v3/store.py', lambda text: replace_once(text,
        "            require(s['lifecycle']['phase'] not in {'blocked', 'completed'}, 'track_not_deliverable')\n",
        '            from dsh_panel_targets import allows_backfill\n'
        "            require(s['lifecycle']['phase'] != 'blocked' and (s['lifecycle']['phase'] != 'completed' or (f['operation'].get('review_manifest', {}).get('intent') == 'specific_episode' and allows_backfill(self.path, s['track_id']))), 'track_not_deliverable')\n"))
    edit('scripts/watch_v3/cli.py', lambda text: replace_once(text,
        "                if show and (show['lifecycle']['phase'] in {'completed','blocked'} or show['progress']['target_episode'] is None):\n",
        '                from dsh_panel_targets import allows_backfill\n'
        "                if show and (show['lifecycle']['phase'] == 'blocked' or ((show['lifecycle']['phase'] == 'completed' or show['progress']['target_episode'] is None) and not allows_backfill(repo.path, show['track_id']))):\n"))
    edit('scripts/package_release.py', lambda text: replace_once(text,
        '    return permit, report, review\n',
        '    from dsh_panel_run import record_found\n'
        '    record_found(report, review=review, review_path=path)\n'
        '    return permit, report, review\n'))

    for path in (target / 'references').glob('*.md'):
        text = path.read_text(encoding='utf-8-sig')
        text = text.replace('automation_update', 'schedule_edit')
        if path.name in {'scheduled-run.md', 'scheduled-retry.md', 'completion.md'}:
            heading, rest = text.split('\n', 1)
            text = heading + '\n\nDSH: first read [dsh-host-runtime.md](dsh-host-runtime.md) for scheduler readback, '
            text += 'state isolation and tool mapping. It replaces Codex-specific host behavior.\n' + rest
        if path.name == 'completion.md':
            text = text.replace('with mode delete', 'with action delete and expectedUpdatedAt from a fresh schedule_view')
            text = text.replace('Current exact scheduler TOML', 'Current exact exported scheduler TOML')
            text = text.replace('The configuration file is read-only evidence, not a scheduler edit interface.',
                'The TOML is generated by dsh_host.py task-snapshot from a fresh schedule_view response. '
                'It is read-only binding evidence, not a DSH scheduler storage file or edit interface.')
        if path.name == 'scheduled-run.md':
            text = text.replace('heartbeat 的 current_time_iso 是触发时间', 'DSH 计划消息的触发时间是触发时间')
        path.write_text(text, encoding='utf-8', newline='\n')

    for path in (ROOT / 'overlays').rglob('*'):
        if path.is_file() and not any(part in EXCLUDED for part in path.parts) and path.suffix != '.pyc':
            destination = target / path.relative_to(ROOT / 'overlays')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    search_guide = (source / 'references/search-flow.md').read_text(encoding='utf-8')
    search_guide = search_guide.replace('python -X utf8 scripts/search_flow.py',
        'python -X utf8 scripts/dsh_panel_run.py --plan-id ID search')
    search_guide = search_guide.replace(' --track-id TRACK_ID --intent latest_regular', '')
    edit('references/panel-search.md', lambda text: replace_once(text, '<!-- SHARED_SEARCH_FLOW -->', search_guide))
    edit('SKILL.md', lambda text: replace_once(text,
        'Run commands from this skill directory. Read the matching workflow and load its\nsupporting references only when needed.',
        'Run commands from the absolute resource directory supplied by DSH, not the chat workspace.\n'
        'Use DSH file/terminal tools and an installed Python 3.11+ (python, python3, or py -3).\n'
        'Default to a DSH full-access session for this skill and use `sandbox_permissions: "danger-full-access"`\n'
        'on terminal calls. Reuse that authorization; do not ask separately for every directory.\n'
        'If the session is restricted, ask once to switch to full access; the skill cannot grant host permissions.\n'
        'Only for an actual environment failure, use `python scripts/dsh_doctor.py` (read-only). No install-time commands run.\n'
        'Never use Codex tools, local Codex records or an assumed model/browser API. For creating\n'
        'or changing schedules and cleanup, read [DSH host integration](references/dsh-host-runtime.md).\n'
        'Read the matching workflow and load supporting references only when needed.'))
    edit('SKILL.md', lambda text: replace_once(text,
        'Provide usage guidance only when the user asks for an introduction or tutorial.\n'
        'A scheduled/background run never opens setup windows.\n'
        'When the user asks to connect Bangumi/enter a token, run\n'
        '`python scripts/setup_gui.py --section bangumi`. For needed local download settings,\n'
        'use `--section qbittorrent` after the existing client-readiness check.\n'
        'Let the user fill the small window; read `--status` after they finish, never read\n'
        "credentials. Use the host's approved visible desktop context, not an isolated\n"
        'sandbox desktop. On `gui_unavailable`, explain the desktop/Tk requirement and offer\n'
        'manual file/env setup. Existing config is not proof of live connection success.',
        'In DSH, use the native Anime tracking panel for plans and Bangumi/qBittorrent\n'
        'configuration. Provide usage guidance only on request; do not open Python\n'
        'setup windows automatically. Optional setup\n'
        'never blocks link-only searches. Headless users may use private file/env setup.\n'
        'For every `[anime-plan:ID]` search, manual or scheduled, start with\n'
        '[panel-search.md](references/panel-search.md), not the generic scheduled-run route below.\n'
        'Read [panel-management.md](references/panel-management.md) for UI/plan management.\n'
        'Panel task execution marks non-watched works as watching; progress and completion\n'
        'writes require a user button click. Keep completed download history locally;\n'
        'this overrides the chat delivery-mirroring and cleanup defaults below.\n'
        'Never request credentials in chat. Background runs do not show onboarding.'))
    manifest = {'upstream': 'https://github.com/divisioncassini05-lab/find-nyaa-anime-release',
                'dsh_contract_commit': 'fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159',
                'source_files': files,
                'adapted_files': ['SKILL.md', 'scripts/runtime_paths.py', 'scripts/qbittorrent_submit.py',
                                  'scripts/watch_v3/automation.py', 'scripts/watch_v3/outbox.py',
                                  'scripts/watch_v3/finalization.py', 'scripts/watch_v3/store.py', 'scripts/watch_v3/workflow.py', 'scripts/watch_v3/cli.py', 'scripts/watch_v3/evidence.py', 'scripts/package_release.py', 'scripts/scheduled_watch.py', 'references/scheduled-new-anime.md',
                                  'references/scheduled-run.md', 'references/scheduled-retry.md', 'references/completion.md'],
                'added_files': [p.relative_to(ROOT / 'overlays').as_posix() for p in sorted((ROOT / 'overlays').rglob('*'), key=lambda item: item.as_posix())
                                if p.is_file() and not any(part in EXCLUDED for part in p.parts) and p.suffix != '.pyc']}
    (output_root / 'UPSTREAM.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    if emit:
        print(json.dumps({'status': 'built', 'files': len(files), 'skill': str(target)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    rebuild(parser.parse_args().source)
