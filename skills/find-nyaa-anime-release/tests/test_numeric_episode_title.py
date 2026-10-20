from decimal import Decimal
from types import SimpleNamespace
import pytest
from test_release_finder import candidate
import release_search_core as core
from release_identity import parse_release_identity, EpisodeKind
from nyaa_client import NyaaFileEntry


def entries():
    names = ['Last.Chance.for.a.Slow.Dance', 'Give.Me.Another.Day', '021',
             'Someone.That.I.Used.To.Know', 'Fades.Pass.the.Distance', 'Everything.Hate',
             'To.the.Depths.With.You', 'Serce', 'Strictly.Reserved.For.You', 'Then.Everyone.Went.Home']
    return [NyaaFileEntry(name=f'Cyberpunk.Edgerunners.S02/Cyberpunk.Edgerunners.S02E{i:02d}.{name}.1080p.NF.WEB-DL.MULTi.DDP5.1.H.264-VARYG.mkv',
                          size='2.4 GiB', size_bytes=int(2.4*1024**3))
            for i, name in enumerate(names, 1)]


def coverage(files, season=2):
    title='Cyberpunk Edgerunners S02 1080p NF WEB-DL MULTi (Batch)'
    item=core.ClassifiedCandidate(candidate(title,'24 GiB',10),parse_release_identity(title),'match',effective_season=2)
    return core._coverage_from_file_entries(item,files,SimpleNamespace(tier='watch'),core.SizePolicy('tier',2,None,2,4),season,10)


def test_numeric_episode_title_complete_season():
    result=coverage(entries())
    assert result.complete and result.quality_fit
    assert result.covered_episodes == tuple(range(1,11))


def test_missing_episode_still_rejected():
    result=coverage([e for e in entries() if 'S02E03.' not in e.name])
    assert not result.complete and result.reason == 'missing_target_episodes:3'


def test_wrong_season_still_rejected():
    assert not coverage(entries(),1).complete


@pytest.mark.parametrize('fraction', ['5','25','125'])
def test_decimal_special_stays_special(fraction):
    result=parse_release_identity(f'Example.S02E03.{fraction}.1080p.WEB.mkv')
    assert result.kind is EpisodeKind.SPECIAL
    assert result.episode == Decimal('3.'+fraction)


def test_below_floor_still_rejected():
    files=entries();files[2]=NyaaFileEntry(name=files[2].name,size='0.5 GiB',size_bytes=2**29)
    result=coverage(files)
    assert result.complete and not result.quality_fit
