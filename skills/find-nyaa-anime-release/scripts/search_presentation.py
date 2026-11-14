"""Bound transport output without interpreting or dropping evidence."""
from __future__ import annotations

import copy
import json

# Below the host's stdout and formatted-result limits, with room for context.
OUTPUT_BYTES = 24000


def encoded_size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def description_blocks(text):
    """Contiguous exact spans, including whitespace; concatenation is lossless."""
    return [text[i:i + 3000] for i in range(0, len(text), 3000)] or ['']


def compact_duplicates(pages, previous=()):
    """Only byte-equivalent displayed rows collapse; changed title/metadata stays."""
    seen = {json.dumps(row, ensure_ascii=False, separators=(',', ':'))
            for page in previous for row in page['values']}
    for page in pages:
        rows = page['values']
        page['values'], page['repeated_ids'] = [], []
        for row in rows:
            signature = json.dumps(row, ensure_ascii=False, separators=(',', ':'))
            if signature in seen:
                page['repeated_ids'].append(row[0])
            else:
                page['values'].append(row)
                seen.add(signature)
    return pages


def split_item(item, fields, budget):
    header = {key: value for key, value in item.items() if key not in fields}
    current = {**header, **{key: [] for key in fields}}
    for field in fields:
        for value in item.get(field, []):
            current[field].append(value)
            if encoded_size(current) <= budget:
                continue
            current[field].pop()
            if any(current[key] for key in fields):
                yield current
                current = {**header, 'continued': True, **{key: [] for key in fields}}
            current[field].append(value)
            if encoded_size(current) > budget:
                raise ValueError('evidence_item_exceeds_transport_budget')
    yield current


def response_parts(response, budget=OUTPUT_BYTES):
    key = 'listings' if 'listings' in response else 'candidates'
    fields = ('values', 'repeated_ids') if key == 'listings' else ('description', 'files')
    base = {name: value for name, value in response.items() if name != key}
    current = {**copy.deepcopy(base), key: []}
    room = budget - encoded_size(current) - 512
    if room <= 0:
        raise ValueError('search_metadata_exceeds_transport_budget')
    for item in response[key]:
        for part in split_item(item, fields, room):
            current[key].append(part)
            if encoded_size(current) <= budget:
                continue
            current[key].pop()
            yield current
            current = {**copy.deepcopy(base), key: [part]}
    yield current
