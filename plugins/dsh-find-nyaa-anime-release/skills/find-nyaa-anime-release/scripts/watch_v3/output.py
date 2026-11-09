"""Compact, lossless evidence views; saved reports keep their original schema."""
from __future__ import annotations


def table(rows):
    if not rows or any(set(row) != set(rows[0]) for row in rows):
        return {'items': rows}
    common = {key: value for key, value in rows[0].items()
              if all(row[key] == value for row in rows[1:])}
    columns = [key for key in rows[0] if key not in common]
    return {'common': common, 'columns': columns,
            'values': [[row[key] for key in columns] for row in rows]}


def compact_report(report):
    """No title, description, filename, row or unknown field is truncated."""
    result = dict(report)
    if report.get('kind') == 'nyaa_listing':
        result['rows'] = table(report['rows'])
        result['view'] = 'compact_table_v1'
    elif report.get('kind') == 'nyaa_detail':
        result['files'] = table(report['files'])
        result['view'] = 'compact_table_v1'
    elif report.get('reviewed') is False and report.get('output_path'):
        return {'status': 'review_draft_saved', 'reviewed': False,
                'output_path': report['output_path'],
                'next_action': 'Read and complete this draft once; it is not approved.'}
    return result
