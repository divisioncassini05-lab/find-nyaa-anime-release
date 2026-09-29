"""Script-form variants are search spellings, never learned work aliases."""
from functools import lru_cache
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'search_dependencies'))
from opencc import OpenCC


@lru_cache(maxsize=2)
def _converter(config: str):
    return OpenCC(config)


def chinese_search_variants(names, max_titles: int = 2) -> list[str]:
    """Try both scripts for at most two known Chinese title families.

    Kana/Hangul names cannot occupy a Chinese-title slot. Conversion supplies
    query text only; callers must retain their original identity context.
    """
    families = set()
    result = []
    for name in names:
        if not name or not re.search(r'[\u3400-\u9fff]', name):
            continue
        if re.search(r'[\u3040-\u30ff\uac00-\ud7af]', name):
            continue
        simplified = _converter('t2s').convert(name)
        if simplified in families:
            continue
        families.add(simplified)
        for variant in (name, simplified, _converter('s2t').convert(simplified)):
            if variant not in result:
                result.append(variant)
        if len(families) >= max_titles:
            break
    return result


def exact_chinese_queries(names, search_titles, episode: int) -> list[str]:
    queries = [f'{name} {episode:02d}' for name in chinese_search_variants(names)]
    # Two verified Latin titles can have different stable anchors (e.g.
    # Jaadugar versus Tenmaku); the latter survives macron/doubled-vowel titles.
    for title in list(dict.fromkeys(search_titles))[:2]:
        tokens = re.findall(r'[A-Za-z0-9]+', title)
        anchor = next((t for t in tokens if len(t) >= 5 and t.lower() not in
                       {'anime', 'season', 'movie', 'the', 'this', 'with'}), None)
        queries.append(f'{anchor or title} {episode:02d}')
    return list(dict.fromkeys(queries))
