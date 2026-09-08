"""Reproducible, offline comparison against reviewed labels, not parser guesses."""
import argparse
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

from identity_adapter import parse_identity, library_parse
from release_identity import parse_legacy_identity
sys.path.insert(0,str(Path(__file__).parent/'parser_dependencies'))
import anitopy


def cases_from_files(labels_path, cache_path):
    labels=json.loads(labels_path.read_text(encoding='utf-8'))
    cache=json.loads(cache_path.read_text(encoding='utf-8'))
    rows={r['release']['nyaa_id']:r['release'] for entry in cache['entries'].values() for r in entry['items']
          if any(t in r['query'] for t in ['Nijusseiki','Sparks'])}
    titles=['二十世纪电气目录','Sparks of Tomorrow','Nijusseiki Denki Mokuroku: Eureka Evrika',
            'Nijusseiki Denki Mokuroku','20 Seiki Denki Mokuroku']
    cases=[{'id':rid,'title':rows[rid]['title'],'episode':ep,'kind':'regular','aliases':titles,'source':'historical_cache'}
           for rid,ep in labels['real'].items()]
    cases.extend(dict(row,id=f'synthetic-{i}',source='constructed_boundary') for i,row in enumerate(labels['synthetic']))
    return cases,rows


def _result(engine,case):
    if engine=='aniparse-adapter':
        r=parse_identity(case['title'],case['aliases'])
        return {'episode':str(r.episode) if r.episode is not None else None,'season':r.season,'kind':r.kind.value,
                'status':r.decision['status'],'evidence':r.decision}
    if engine=='legacy':
        r=parse_legacy_identity(case['title'])
        return {'episode':str(r.episode) if r.episode is not None else None,'season':r.season,'kind':r.kind.value}
    if engine=='aniparse-raw':
        parsed=library_parse(case['title']); series=parsed.get('series',[])
        episodes=[e['number'] for s in series for e in s.get('episode',[]) if 'number' in e]
        seasons=[s['number'] for r in series for s in r.get('season',[]) if 'number' in s]
        return {'episode':str(episodes[0]) if len(episodes)==1 else None,'season':seasons[0] if len(seasons)==1 else None,
                'kind':None, 'raw':parsed}
    r=anitopy.parse(case['title']); ep=r.get('episode_number')
    return {'episode':str(ep) if ep is not None and not isinstance(ep,list) else None,
            'season':int(r['anime_season']) if str(r.get('anime_season','')).isdigit() else None,'kind':None,'raw':r}


def benchmark(labels,cache):
    cases,rows=cases_from_files(labels,cache)
    output={'cache_sha256':hashlib.sha256(cache.read_bytes()).hexdigest(),
            'recovered_unique_records':len(rows),'labelled_cases':len(cases),'engines':{}}
    for engine in ['legacy','anitopy','aniparse-raw','aniparse-adapter']:
        counts={'wrong_match':0,'missed_match':0,'needs_review':0,'correct':0}
        results=[]
        for case in cases:
            result=_result(engine,case)
            expected=case.get('episode')
            wrong=False; missed=False
            if 'episode' in case:
                got=result['episode']
                wrong=got is not None and (expected is None or Decimal(got)!=Decimal(str(expected)))
                missed=got is None and expected is not None
            if case.get('season') is not None:
                wrong=wrong or (result['season'] is not None and result['season']!=case['season'])
                missed=missed or result['season'] is None
            if engine in {'legacy','aniparse-adapter'}:
                wrong=wrong or result['kind']!=case['kind']
            if engine=='aniparse-adapter' and case.get('status'):
                wrong=wrong or result.get('status')!=case['status']
            outcome='wrong_match' if wrong else 'missed_match' if missed else 'correct'
            counts[outcome]+=1
            if result.get('status') in {'unresolved','conflict'}:
                counts['needs_review']+=1
            results.append({'id':case['id'],'title':case['title'],'expected':{k:v for k,v in case.items() if k in {'episode','season','kind','status'}},'outcome':outcome,'actual':result})
        output['engines'][engine]={'counts':counts,'cases':results}
    output['gate_passed']=all(output['engines']['aniparse-adapter']['counts'][k]==0 for k in ['wrong_match','missed_match'])
    output['scope']='Reviewed labels only; raw libraries evaluated on number extraction, adapters additionally on kind. Not a universal accuracy estimate.'
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--labels',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();report=benchmark(args.labels,args.cache)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='engines'},ensure_ascii=False))
    print(json.dumps({k:v['counts'] for k,v in report['engines'].items()},ensure_ascii=False))
    raise SystemExit(0 if report['gate_passed'] else 1)
