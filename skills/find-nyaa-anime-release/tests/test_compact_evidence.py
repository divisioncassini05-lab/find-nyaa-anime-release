import copy
import json

import pytest

from watch_v3.output import compact_report, table


def expand(value):
    if 'items' in value:
        return value['items']
    return [{**value['common'], **dict(zip(value['columns'], row))} for row in value['values']]


@pytest.mark.parametrize('rows', [[], [{'id': 1}], [{'id': 1}, {'id': 1}],
                                [{'id': 1}, {'id': 2, 'extra': None}]])
def test_table_is_lossless_for_edge_shapes(rows):
    assert expand(table(rows)) == rows


def test_full_listing_order_unknown_fields_and_all_rows_survive_compaction():
    rows = [dict(nyaa_id=str(i), title=f'Atlas Chronicle - {i:02} [Subtitles]',
                 url=f'https://nyaa.si/view/{i}', size_bytes=1500000000, size_text='1.4 GiB',
                 seeders=i, leechers=4, downloads=100, pub_date='2026-01-02T00:00:00Z',
                 category='1_2', trusted=False, remake=False, info_hash=None, future_field='preserved')
            for i in range(75, 0, -1)]
    raw = dict(kind='nyaa_listing', row_count=75, rows=rows, later_pages=[2, 3], scope='this_query_and_page_only')
    before = copy.deepcopy(raw)
    compact = compact_report(raw)
    assert expand(compact['rows']) == rows
    assert {k: v for k, v in compact.items() if k not in {'rows', 'view'}} == {k: v for k, v in raw.items() if k != 'rows'}
    assert raw == before
    assert len(json.dumps(compact, separators=(',', ':'))) < len(json.dumps(raw, indent=2)) * .55


def test_description_and_every_file_remain_available():
    raw = dict(kind='nyaa_detail', description='Subtitles: Chinese\n' + 'Long description ' * 500,
               release={'title': 'Atlas Complete'}, files=[{'name': f'E{i:02}.mkv', 'size_bytes': i * 100} for i in range(100)])
    result = compact_report(raw)
    assert result['description'] == raw['description']
    assert expand(result['files']) == raw['files']


def test_draft_receipt_never_claims_approval():
    result = compact_report({'reviewed': False, 'output_path': '/draft.json', 'selection': {}})
    assert result['status'] == 'review_draft_saved'
    assert result['reviewed'] is False
    assert result['output_path'] == '/draft.json'
    assert 'selection' not in result


def test_cli_compact_is_opt_in_and_saved_schema_unchanged(tmp_path, monkeypatch, capsys):
    from watch_v3 import cli
    from evidence_artifacts import new_workspace
    state = tmp_path / 'state.json'
    run_dir = new_workspace(state)
    raw = dict(schema_version=1, kind='nyaa_detail', release={'title': 'Atlas'},
               description='Subtitles: Chinese', files=[{'name': 'E01.mkv', 'size_bytes': 1234}])
    monkeypatch.setattr(cli.DiscoveryService, 'detail', lambda *_: copy.deepcopy(raw))
    output = run_dir / 'detail.json'
    args = ['--state', str(state), 'detail', '123', '--output', str(output)]
    assert cli.run([*args, '--compact']) == 0
    result = json.loads(capsys.readouterr().out)
    assert expand(result['files']) == raw['files']
    assert json.loads(output.read_text(encoding='utf-8')) == raw
    assert cli.run(args) == 0
    assert json.loads(capsys.readouterr().out)['files'] == raw['files']
