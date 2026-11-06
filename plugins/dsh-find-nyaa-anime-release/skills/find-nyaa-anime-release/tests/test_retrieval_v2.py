from __future__ import annotations
import argparse
import json
from pathlib import Path
from unittest.mock import patch, Mock
import pytest
from test_reviewed_finalization import run_finder, release
from test_release_finder import search_args
import release_search_core as core
import find_anime_release as finder
import anime_release.providers as v2_providers
from release_identity import parse_release_identity
from offline_identity import import_aod, import_anime_lists, lookup, map_episode
from benchmark_retrieval import benchmark


def test_reviewed_corpus_passes():
    root=Path(__file__).resolve().parents[1]
    report=benchmark(root/'tests/fixtures/retrieval_cases.json',root/'tests/fixtures/historical-cache.json')
    assert report['recovered_unique_records']==129
    assert report['gate_passed'],report['engines']['aniparse-adapter']['counts']


def test_unpinned_latest_unqualified_keeps_target_and_full_evidence(tmp_path):
    releases=[release(100,episode=9),*[release(200+i,episode=10,size='0.5 GiB') for i in range(5)]]
    _,r,submit,before,_=run_finder(tmp_path,releases,['--latest','--no-state-update'],watched=9)
    assert r['target_episode']==10
    assert r['target_decision']['confirmed_episode']==10
    assert r['availability']['state']=='release_unqualified'
    assert r['choice_count']==5 and r['choices_returned']==2 and r['choices_truncated']
    assert len(r['search_run']['raw_candidates'])==6
    assert '10' in r['reply_text']
    assert (tmp_path/'state.json').read_bytes()==before
    submit.assert_not_called()


def test_unreviewed_enqueue_stops_before_client(tmp_path):
    _,r,submit,before,_=run_finder(tmp_path,[release()],['--latest','--enqueue-qbittorrent'])
    assert r['status']=='review_required'
    assert r['qbittorrent']['status']=='not_attempted'
    submit.assert_not_called()
    assert (tmp_path/'state.json').read_bytes()==before


def test_failed_alias_cannot_prove_latest(tmp_path):
    _,r,submit,before,_=run_finder(tmp_path,[release()],['--latest','--no-state-update'],failures=['second title: timeout'])
    assert r['target_decision']['confirmed_episode'] is None
    assert r['search_run']['completeness']=='partial'
    submit.assert_not_called()
    assert (tmp_path/'state.json').read_bytes()==before


def test_unknown_higher_number_not_promoted_by_same_episode():
    known=parse_release_identity('Show S01E10',['Show'])
    weak=parse_release_identity('Something 10')
    a=core.ClassifiedCandidate(release(),known,'match')
    b=core.ClassifiedCandidate(release(202),weak,'match')
    assert core._latest_regular([a,b])==[a]


def test_known_numeric_title_is_protected():
    r=parse_release_identity('20 Seiki Denki Mokuroku 10 [1080p]',['20 Seiki Denki Mokuroku'])
    assert r.episode==10
    assert any(x['field']=='title' and x['span']==[0,23] for x in r.decision['evidence'])


def test_conflicting_explicit_numbers_block_latest(tmp_path):
    _,r,submit,_,_=run_finder(tmp_path,[release(),release(202,title='Example Anime S01E06 E07')],['--latest','--no-state-update'])
    assert r['status']=='latest_unresolved'
    assert r['target_decision']['confirmed_episode'] is None
    submit.assert_not_called()


def test_offline_ids_do_not_merge_related_or_conflicting_records():
    rows=import_aod({'data':[{'title':'Example','sources':['https://anilist.co/anime/12','https://anidb.net/anime/44'],
                             'synonyms':['English Example'],'type':'TV'}]},'pinned:aod','2026-09-07')
    assert lookup({'entries':rows},[('anilist',12)])['aliases']==['Example','English Example']
    assert lookup({'entries':rows},[('anilist',12),('anidb',99)])['aliases']==[]
    assert lookup({'entries':rows},[('anilist',13)])['aliases']==[]


def test_explicit_offline_numbering_mapping_only():
    xml='<anime-list><anime anidbid="44" tvdbid="12"><name>Example</name><mapping-list><mapping start="13" end="24" offset="-12" tvdbseason="2" /></mapping-list></anime></anime-list>'
    rows=import_anime_lists(xml,'pinned:anime-lists','2026-09-07')
    mappings=rows[0]['mappings']
    assert map_episode(15,mappings,'anidb','tvdb')==(2,3)
    assert map_episode(25,mappings,'anidb','tvdb') is None
    assert map_episode(15,mappings,'tvdb','anidb') is None


def test_quality_is_evaluated_after_latest(tmp_path):
    _,r,submit,_,_=run_finder(tmp_path,[release(),release(202,episode=6,size='0.5 GiB')],['--latest','--candidate-id','101','--no-state-update'])
    assert r['target_episode']==6
    assert r['selected'] is None
    submit.assert_not_called()


def test_actual_query_errors_are_preserved():
    args=search_args();args.query='Example';args.alias=['Other'];args.intent='latest_regular';args.season='S01'
    client=Mock();client.search.side_effect=TimeoutError('fixture timeout')
    result=core.search_release_report(args,intent='latest_regular',client=client)
    assert len(result.search_run.requests)==2
    assert all(r['status']=='failed' for r in result.search_run.requests)
    assert result.search_run.completeness=='partial'


def test_cached_latest_query_is_broad_even_if_schedule_says_older(tmp_path):
    args=search_args();args.query='Example Anime';args.alias=[];args.episode=5;args.season='S01'
    releases=[release(101,episode=5),release(202,episode=6)]
    ctx=core.SearchContext(canonical_title='Example Anime',mainline_scope='single',resolved_season=1)
    with patch.object(core,'collect_raw_candidates',return_value=(releases,[],'fixture')) as collect:
        r=core.search_release_report(args,intent='latest_regular',requested_episode=5,context=ctx)
    assert collect.call_args.args[0].episode is None
    assert r.requested_episode==6


def test_schedule_failure_with_known_identity_does_not_prevent_search(tmp_path):
    # Exercise hydration fallback with a 403, preserving an independently known work.
    from urllib.error import HTTPError
    resolved=finder.ResolvedAnime(title='Example Anime',search_titles=['Example Anime'],
                                 anilist_id=12,season='S01',current=True,trackable=True,status='RELEASING',format='TV')
    with patch.object(v2_providers,'anilist_media_request',side_effect=HTTPError('https://example.test',403,'Forbidden',{},None)):
        hydrated,status=finder.hydrate_airing_metadata(resolved,1,tmp_path/'schedule.json',True,finder.date.today())
    assert hydrated.title==resolved.title
    assert status=='unavailable'


def test_lower_episode_conflict_does_not_block_confirmed_newer_target(tmp_path):
    _,r,submit,_,_=run_finder(tmp_path,[release(101,episode=10),release(202,title='Example Anime S01E06 E07')],['--latest','--no-state-update'])
    assert r['target_episode']==10 and r['status']=='found'
    submit.assert_not_called()


def test_special_number_does_not_raise_latest_observation(tmp_path):
    _,r,_,_,_=run_finder(tmp_path,[release(101,episode=10),release(202,title='Example Anime S01E99 OVA')],['--latest','--no-state-update'])
    assert r['target_decision']['observed_episode']==10
    assert r['target_decision']['confirmed_episode']==10


@pytest.mark.parametrize('title', ['Show Season 4 S03E10', 'Show S01E10 E11'])
def test_conflicting_identity_cannot_be_accepted_as_exact(title):
    ident=parse_release_identity(title,['Show Season 4','Show'])
    assert ident.decision['status']=='conflict'
    item=core.ClassifiedCandidate(release(title=title),ident,'match')
    assert not core._is_exact_regular_episode(item,10)


@pytest.mark.parametrize('token',['1080','2026','12345678'])
def test_metadata_brackets_are_not_episode_numbers(token):
    assert parse_release_identity(f'Show [{token}] [HEVC]',['Show']).episode is None


def test_four_digit_absolute_episode_survives_brackets():
    assert parse_release_identity('One Piece [1123] [1080p]',['One Piece']).episode==1123


def test_query_page_failure_retains_previous_raw_rows():
    from nyaa_client import NyaaRelease
    args=search_args();args.query='Example';args.season='S01';args.episode=10
    args.alias=[];args.candidate_id=[]
    rows=[NyaaRelease(str(i),f'Example S01E09 [{i:08x}]','Anime','0.5 GiB',536870912,
        None,None,1,0,0,f'https://nyaa.si/view/{i}') for i in range(75)]
    network=Mock();network.search.side_effect=[rows,TimeoutError('second page failed'),[],[]]
    report=core.search_release_report(args,intent='specific_episode',requested_episode=10,client=network)
    assert len(report.search_run.raw_candidates)==75
    assert report.search_run.completeness=='partial'
    assert any(r.get('status')=='failed' for r in report.search_run.requests)


def test_hash_dedup_does_not_depend_on_magnet_output():
    from nyaa_client import NyaaRelease
    from dataclasses import asdict
    rows=[{'query':f'alias{i}','release':asdict(NyaaRelease(str(i),'Example S01E01','Anime','1.4 GiB',1503238553,
        None,None,1,0,0,f'https://nyaa.si/view/{i}','a'*40))} for i in (1,2)]
    result=core._score_rss_items(rows,search_args())
    assert len(result)==1
    assert result[0].matched_queries==['alias1','alias2']
    assert result[0].magnet is None


def test_mapping_bridge_is_exact_work_id_not_shared_franchise_id():
    from offline_identity import combine_catalogs
    primary=[{'ids':{'anilist':12,'anidb':44},'aliases':['Example'],'source':'aod','updated_at':'2026-07-04','mappings':[]}]
    mapped=import_anime_lists('<anime-list><anime anidbid="44" tvdbid="999"><mapping-list><mapping anidbseason="1" start="13" end="24" offset="-12" tvdbseason="2"/></mapping-list></anime></anime-list>','anime-list:sha','2026-09-07')
    merged=combine_catalogs(primary,mapped)
    assert map_episode(15,lookup({'entries':merged},[('anilist',12)])['mappings'],'anidb','tvdb')==(2,3)
    mapped[0]['ids']['anidb']=45
    assert combine_catalogs(primary,mapped)==primary


def test_special_mapping_is_never_applied_to_regular_episode():
    xml='<anime-list><anime anidbid="44"><mapping-list><mapping anidbseason="0" start="1" end="10" offset="0" tvdbseason="1"/></mapping-list></anime></anime-list>'
    assert import_anime_lists(xml,'pinned','2026-09-07')[0]['mappings']==[]


def test_pinned_detail_failure_cannot_fall_back_to_cached_candidate(tmp_path):
    from nyaa_client import NyaaClient
    network=Mock(spec=NyaaClient);network.get.side_effect=TimeoutError('detail unavailable')
    _,r,submit,before,_=run_finder(tmp_path,[release()],['--latest','--candidate-id','101','--enqueue-qbittorrent'],client=network)
    assert r['status']!='found'
    assert r['target_episode']==5
    assert r['target_decision']['confirmed_episode']==5
    submit.assert_not_called()
    assert (tmp_path/'state.json').read_bytes()==before


def test_live_work_id_and_episode_are_not_guessed_from_similar_title(tmp_path):
    _,r,submit,_,_=run_finder(tmp_path,[release(title='Other Anime S01E05')],['--episode','5','--no-state-update'])
    assert r['status']!='found'
    submit.assert_not_called()


def test_movie_compatibility_without_mixing_trailers_into_regular():
    movie=parse_release_identity('Show Movie [1080p]',['Show'])
    trailer=parse_release_identity('Show Movie Trailer [1080p]',['Show'])
    assert core._is_movie_identity(movie)
    assert not core._is_movie_identity(trailer)
    assert movie.kind is not core.EpisodeKind.REGULAR
