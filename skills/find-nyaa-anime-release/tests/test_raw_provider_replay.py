"""Raw captured provider/HTML/RSS bodies through the actual CLI and parsers.

Only network IO is substituted; identity, episode selection, filtering and state
serialization are real. Fixtures captured 2026-09-24, not manufactured resolutions.
"""
import contextlib
import io
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import pytest

import find_anime_release as finder
import anime_release.providers as providers
import anime_release.workflow as workflow
import search_nyaa_releases as search
import release_search_core as core
from anime_release.storage import atomic_json
from anime_release.repository import StateRepository

FIXTURES = Path(__file__).parent/'fixtures/provider-replay'

def raw(name):
    return json.loads((FIXTURES/(name+'.json')).read_text(encoding='utf-8'))['response']

def replay(tmp_path, monkeypatch, *, wrong=False, aliases=False, options=()):
    media = raw('anilist-re0-s4')['data']['Media']
    path = tmp_path/'state.json'
    show = {'title':media['title']['english'],'aliases':[media['title']['romaji'],media['title']['native'],
            're0','Re:从零开始的异世界生活'],'season':'S04','format':'TV', 'anilist_id':21355 if wrong else 189046,
            'search_titles':['Re ZERO kara Hajimeru Isekai Seikatsu'], 'watched_episode':17,
            'latest_known_episode':17,'next_episode':18,'status':'airing','airing':True}
    atomic_json(path,{'version':1,'shows':[show]})
    before = path.read_bytes()
    calls=[]
    def anilist_id(media_id, timeout):
        calls.append(('id',media_id))
        return raw('anilist-re0-s1' if media_id==21355 else 'anilist-re0-s4')
    def anilist_query(query, timeout):
        calls.append(('anilist',query))
        return raw('anilist-re0-search')
    def bangumi_query(query, timeout):
        calls.append(('bangumi',query))
        return raw('bangumi-re0-search')
    def nyaa_response(url, timeout):
        calls.append(('nyaa',url))
        if '/view/' in url:
            if url.endswith('/2165262'):
                return (FIXTURES/'re0-2165262.html').read_bytes()
            from nyaa_client import NyaaNetworkError
            raise NyaaNetworkError('Detail response not captured; no fabricated verification')
        params=parse_qs(urlsplit(url).query)
        return (FIXTURES/('re0-rss.xml' if params.get('page')==['rss'] else 're0-listing.html')).read_bytes()
    monkeypatch.setattr(providers,'anilist_media_request',anilist_id)
    monkeypatch.setattr(providers,'anilist_request',anilist_query)
    monkeypatch.setattr(providers,'bangumi_request',bangumi_query)
    monkeypatch.setattr(search._TRANSPORT_CLIENT,'_request',nyaa_response)
    monkeypatch.setattr(core.DEFAULT_NYAA_CLIENT,'_request',nyaa_response)
    monkeypatch.setattr(workflow,'submit_magnet',lambda *a,**k:pytest.fail('Replay may not enqueue'))
    output=io.StringIO()
    with contextlib.redirect_stdout(output):
        code=finder.main(['Re:从零开始的异世界生活' if aliases else 're0','--latest','--no-state-update',
            '--state',str(path),'--cache',str(tmp_path/'raw.json'),'--schedule-cache',str(tmp_path/'schedule.json'),
            '--tier','browse','--json','--explain','--want-zh',*options])
    return code,json.loads(output.getvalue()),calls,before==path.read_bytes()

@pytest.mark.parametrize('aliases',[False,True])
def test_current_fourth_season_and_latest_remain_fixed(tmp_path,monkeypatch,aliases):
    code,report,calls,same=replay(tmp_path,monkeypatch,aliases=aliases)
    assert same and code==0
    assert report['season']=='S04' and report['target_episode']==18
    assert report['work_identity']['anilist_id']==189046
    assert report['selected'] and '18' in report['selected']['title']
    assert ('id',189046) in calls and not any(c[0]=='anilist' for c in calls)

def test_raw_first_season_bad_binding_cannot_be_repaired_by_partial_cour(tmp_path,monkeypatch):
    code,report,calls,same=replay(tmp_path,monkeypatch,wrong=True)
    assert same and report['status']=='identity_conflict'
    assert report['season']=='S04' and report['selected'] is None
    assert sum(c[0]=='anilist' for c in calls)==1 and sum(c[0]=='bangumi' for c in calls)==1
    assert not any(c[0]=='nyaa' for c in calls)

def test_newest_under_size_floor_does_not_return_previous_episode(tmp_path,monkeypatch):
    code,report,calls,same=replay(tmp_path,monkeypatch,options=['--min-gib-per-episode','10'])
    assert same and report['target_episode']==18
    assert report['status'] in {'release_unqualified','subtitle_unqualified','no_nyaa_release_for_target'}
    assert report['selected'] is None

def test_raw_pinned_detail_chinese_requirement_cannot_be_invented(tmp_path,monkeypatch):
    code,report,calls,same=replay(tmp_path,monkeypatch,options=['--candidate-id','2165262','--require-zh',
        '--include-magnet','--legal-ok','--enqueue-qbittorrent'])
    assert same and report['target_episode']==18
    assert report['status'] in {'subtitle_unqualified','subtitle_check_incomplete'}

def test_explicit_first_season_filters_current_installment_before_ranking(monkeypatch):
    from datetime import date
    responses = raw('anilist-re0-broad-search')
    monkeypatch.setattr(providers, 'anilist_request', lambda *a, **k: responses)
    status, resolved = providers.resolve_title('Re:Zero kara Hajimeru Isekai Seikatsu', 10,
        date(2026,9,24), season='S01')
    assert status == 'resolved'
    assert resolved.anilist_id == 21355
    assert all(e.season in (None, 'S01') for e in resolved.evidence)
