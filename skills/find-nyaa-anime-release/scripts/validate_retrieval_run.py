"""Run the real high-level CLI read-only with isolated state/cache and saved evidence."""
from __future__ import annotations
import argparse
from contextlib import ExitStack, redirect_stdout
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch
import find_anime_release as finder
import release_search_core as core
from nyaa_client import NyaaRelease


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--historical-cache',type=Path)
    p.add_argument('--candidate-id')
    p.add_argument('--offline-catalog',type=Path)
    args=p.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    before=args.state.read_bytes()
    snapshot=args.output_dir/'state.json'
    snapshot.write_bytes(before)
    argv=['二十世纪电气目录','--latest','--want-zh','--no-state-update','--json','--explain',
          '--state',str(snapshot),'--cache',str(args.output_dir/'raw-cache.json'),
          '--schedule-cache',str(args.output_dir/'schedule-cache.json'),'--timeout','15','--refresh-cache']
    if args.offline_catalog:
        argv.extend(['--offline-catalog',str(args.offline_catalog)])
    if args.candidate_id:
        argv.extend(['--candidate-id',args.candidate_id,'--include-magnet','--legal-ok'])
    output=io.StringIO()
    with ExitStack() as stack:
        stack.enter_context(patch.object(finder,'submit_magnet',side_effect=AssertionError('Validation must never enqueue')))
        if args.historical_cache:
            cache=json.loads(args.historical_cache.read_text(encoding='utf-8'))
            items=[i for e in cache['entries'].values() for i in e['items']]
            valid={f.name for f in fields(NyaaRelease)}
            def search(request):
                unique={i['release']['nyaa_id']:i['release'] for i in items if i['query']==request.query}
                return [NyaaRelease(**{k:v for k,v in r.items() if k in valid}) for r in unique.values()]
            stack.enter_context(patch.object(core.DEFAULT_NYAA_CLIENT,'search',side_effect=search))
            stack.enter_context(patch.object(core.DEFAULT_NYAA_CLIENT,'get',side_effect=AssertionError('Historical replay has no detail evidence')))
            stack.enter_context(patch.object(core.DEFAULT_NYAA_CLIENT,'get_description',side_effect=AssertionError('Historical replay has no detail evidence')))
            argv.extend(['--no-web-resolve'])
        with redirect_stdout(output):
            code=finder.main(argv)
    report=json.loads(output.getvalue())
    report['validation']={'at':datetime.now(timezone.utc).isoformat(), 'mode':'historical_replay' if args.historical_cache else 'readonly_online',
        'state_sha256':hashlib.sha256(before).hexdigest(),'original_state_unchanged':before==args.state.read_bytes(),
        'isolated_state_unchanged':before==snapshot.read_bytes(),'enqueue_calls':0,'exit_code':code}
    (args.output_dir/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ['status','target_episode','target_decision','validation']},ensure_ascii=False))
    run=report.get('search_run') or {}
    print(json.dumps({'raw_count':len(run.get('raw_candidates',[])),'failures':report.get('failures'),
        'selected': {k:report['selected'].get(k) for k in ['title','url','size','detail_checked']} if report.get('selected') else None},ensure_ascii=False))
    if not all(report['validation'][k] for k in ['original_state_unchanged','isolated_state_unchanged']):
        raise SystemExit('State changed during read-only verification')


if __name__=='__main__':
    main()
