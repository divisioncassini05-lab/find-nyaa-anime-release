"""Build a pinned AOD subset for known AniList IDs; performs metadata GETs only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
from offline_identity import import_aod

AOD_RELEASE='2026-27'
AOD_URL=f'https://github.com/manami-project/anime-offline-database/releases/download/{AOD_RELEASE}/anime-offline-database-minified.json'


def get(url):
    with urlopen(Request(url,headers={'User-Agent':'AnimeRetrievalAudit/2'}),timeout=45) as response:
        return response.read()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--artifact-dir',type=Path,required=True)
    args=p.parse_args()
    args.artifact_dir.mkdir(parents=True,exist_ok=True)
    payload=get(AOD_URL)
    data=json.loads(payload)
    state=json.loads(args.state.read_text(encoding='utf-8'))
    ids={int(s['anilist_id']) for s in state.get('shows',[]) if s.get('anilist_id')}
    subset=[r for r in data['data'] if any(u.rstrip('/').rsplit('/',1)[-1].isdigit()
        and int(u.rstrip('/').rsplit('/',1)[-1]) in ids and u.startswith('https://anilist.co/anime/')
        for u in r.get('sources',[]))]
    entries=import_aod({'data':subset},AOD_URL,data['lastUpdate'])
    # Resolve the named release to a commit for its license, not the moving branch.
    release=json.loads(get(f'https://api.github.com/repos/manami-project/anime-offline-database/commits/{AOD_RELEASE}'))
    commit=release['sha']
    license_url=f'https://raw.githubusercontent.com/manami-project/anime-offline-database/{commit}/LICENSE'
    license_bytes=get(license_url)
    manifest={'version':1,'imported_at':datetime.now(timezone.utc).isoformat(),'entries':entries,
        'license':data['license'],'license_source':license_url,'source':AOD_URL,'release':AOD_RELEASE,
        'source_sha256':hashlib.sha256(payload).hexdigest(),'last_update':data['lastUpdate'],
        'scope':'Known tracked AniList IDs only. Identity/aliases, never airing or publication evidence.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output.parent/'AOD-LICENSE.txt').write_bytes(license_bytes)
    (args.artifact_dir/'aod-source-subset.json').write_text(json.dumps({'license':data['license'],
        'lastUpdate':data['lastUpdate'],'data':subset},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k!='entries'},ensure_ascii=False))
    print(json.dumps({'requested_ids':sorted(ids),'matched_ids':[r['ids'].get('anilist') for r in entries]},ensure_ascii=False))


if __name__=='__main__':
    main()
