"""Source-stamped offline identity supplements; never an airing/release oracle.

Imports anime-offline-database JSON and Anime-Lists XML into one small contract.
Conflicting IDs/aliases stay separate. No similarity-based record merging.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HOSTS = {'anilist.co':'anilist','anidb.net':'anidb','myanimelist.net':'mal',
         'bangumi.tv':'bangumi','bgm.tv':'bangumi','thetvdb.com':'tvdb'}


def read_catalog(path):
    if not path or not Path(path).exists():
        return {'version':1,'entries':[]}
    result = json.loads(Path(path).read_text(encoding='utf-8'))
    if result.get('version') != 1 or not isinstance(result.get('entries'),list):
        raise ValueError('unsupported offline identity catalog')
    return result


def lookup(catalog, identifiers):
    ids = dict(identifiers)
    matches = [r for r in catalog['entries'] if any(r.get('ids',{}).get(k)==v for k,v in ids.items())]
    accepted, conflicts = [],[]
    for row in matches:
        if any(k in ids and ids[k] != v for k,v in row.get('ids',{}).items()):
            conflicts.append(row)
        else:
            accepted.append(row)
    # A shared ID may be split over seasons; only return a unique identity row.
    if len(accepted)>1:
        return {'aliases':[], 'mappings':[], 'sources':[], 'conflicts':['multiple_identity_rows']}
    return {'aliases':accepted[0].get('aliases',[]) if accepted else [],
            'mappings':accepted[0].get('mappings',[]) if accepted else [],
            'sources':[{'source':r.get('source'),'updated_at':r.get('updated_at'),
                        'mapping_sources':r.get('mapping_sources',[])} for r in accepted],
            'conflicts':['inconsistent_ids'] if conflicts else []}


def combine_catalogs(primary, mapping_rows):
    """Join only exact AniDB work IDs, never TVDB franchise IDs or title similarity."""
    from copy import deepcopy
    rows = deepcopy(primary)
    for mapping in mapping_rows:
        aid = mapping.get('ids',{}).get('anidb')
        targets = [r for r in rows if aid and r.get('ids',{}).get('anidb') == aid]
        if len(targets) != 1:
            continue
        target = targets[0]
        if any(k in target['ids'] and target['ids'][k] != v for k,v in mapping['ids'].items()):
            continue
        target['ids'].update(mapping['ids'])
        target['mappings'].extend(mapping.get('mappings',[]))
        target.setdefault('mapping_sources',[]).append({'source':mapping['source'],'updated_at':mapping['updated_at']})
    return rows


def import_aod(data, source, updated):
    entries = []
    for row in data.get('data',[]):
        ids = {}
        for url in row.get('sources',[]):
            for host,namespace in HOSTS.items():
                if re.match(r'https?://(?:www\.)?'+re.escape(host)+r'/',url):
                    m = re.search(r'(\d+)(?:/|$)',url)
                    if m:
                        ids[namespace] = int(m.group(1))
        if ids:
            entries.append({'ids':ids,'aliases':list(dict.fromkeys([row['title'],*row.get('synonyms',[])])),
                            'type':row.get('type'),'source':source,'updated_at':updated,'mappings':[]})
    return entries


def import_anime_lists(xml, source, updated):
    entries=[]
    for row in ET.fromstring(xml).findall('anime'):
        ids={k:int(row.attrib[attr]) for k,attr in [('anidb','anidbid'),('tvdb','tvdbid')]
             if row.attrib.get(attr,'').isdigit()}
        if 'anidb' not in ids:
            continue
        mappings=[]
        for mapping in row.findall('./mapping-list/mapping'):
            # The CLI's AniDB numbering lane is regular-season numbering only.
            if mapping.get('anidbseason','1') != '1':
                continue
            if all(mapping.get(k,'').lstrip('-').isdigit() for k in ['start','end','offset','tvdbseason']):
                mappings.append({'source_numbering':'anidb','target_numbering':'tvdb',
                    'start':int(mapping.get('start')),'end':int(mapping.get('end')),
                    'offset':int(mapping.get('offset')),'season':int(mapping.get('tvdbseason')),
                    'source':source,'updated_at':updated})
        entries.append({'ids':ids,'aliases':[row.findtext('name','')],'source':source,
                        'updated_at':updated,'mappings':mappings})
    return entries


def map_episode(episode, mappings, source_numbering, target_numbering):
    matches=[m for m in mappings if m['source_numbering']==source_numbering and m['target_numbering']==target_numbering
             and m['start'] <= episode <= m['end']]
    values={(m['season'],episode+m['offset']) for m in matches if m['season'] > 0 and episode+m['offset'] > 0}
    return next(iter(values)) if len(values)==1 else None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path)
    p.add_argument('--format',choices=['aod','anime-lists'],required=True)
    p.add_argument('--source',required=True,help='Pinned release URL or commit permalink')
    p.add_argument('--updated-at',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--merge-with',type=Path,help='Existing AOD catalog; joins Anime-Lists through exact AniDB IDs')
    args=p.parse_args()
    raw=args.input.read_text(encoding='utf-8')
    entries=import_aod(json.loads(raw),args.source,args.updated_at) if args.format=='aod' else import_anime_lists(raw,args.source,args.updated_at)
    if args.merge_with:
        if args.format != 'anime-lists':
            p.error('--merge-with is only supported for anime-lists imports')
        entries=combine_catalogs(read_catalog(args.merge_with)['entries'], entries)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'version':1,'imported_at':datetime.now(timezone.utc).isoformat(),'entries':entries},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    main()
