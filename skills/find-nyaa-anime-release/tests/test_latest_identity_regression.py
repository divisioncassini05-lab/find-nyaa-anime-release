from test_release_finder import candidate
import release_search_core as core
from release_identity import Confidence, parse_release_identity


def item(title):
    return core.ClassifiedCandidate(candidate(title, '1.2 GiB', 10), parse_release_identity(title), 'match')


def test_multilingual_title_number_is_not_episode():
    title = '[喵萌奶茶屋&LoliHouse] 二十世纪电气目录 / 20 Seiki Denki Mokuroku / Nijusseiki Denki Mokuroku - 03 [WebRip 1080p HEVC-10bit AAC][简繁日内封字幕]'
    identity = parse_release_identity(title)
    assert identity.episode == 3
    assert identity.episode_confidence is Confidence.EXPLICIT


def test_latest_uses_real_episode_after_multilingual_parse():
    releases = [item('20 Seiki Denki Mokuroku - 03 [1080p]'), item('Sparks of Tomorrow S01E10 [1080p]')]
    assert core._latest_regular(releases) == [releases[1]]


def test_title_only_number_does_not_block_confirmed_release():
    releases = [item('Sparks S01E09'), item('20 Seiki Denki Mokuroku')]
    assert core._latest_regular(releases) == [releases[0]]


def test_weak_only_does_not_establish_latest():
    assert core._latest_regular([item('Show 10')]) == []


def test_explicit_same_episode_does_not_promote_weak_observation():
    releases = [item('Show 10'), item('Show S01E10')]
    assert core._latest_regular(releases) == [releases[1]]
