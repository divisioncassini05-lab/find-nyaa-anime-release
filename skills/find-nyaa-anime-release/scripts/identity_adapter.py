"""Aniparse hypotheses + known title spans + deterministic structural evidence.

Library confidence is not an acceptance probability. Each accepted number must
have a structural witness outside an independently known title span.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
import re
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).parent / 'parser_dependencies'))
import aniparse

from retrieval_decisions import IdentityDecision, TITLE_CONTEXT


@lru_cache(maxsize=2048)
def library_parse(title):
    return aniparse.parse(title) or {}


def title_spans(title, aliases):
    spans = []
    for alias in sorted(set(aliases), key=len, reverse=True):
        tokens = re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', alias), re.UNICODE)
        if not tokens:
            continue
        pattern = r'(?<!\w)' + r'[\W_]*'.join(re.escape(t) for t in tokens) + r'(?!\w)'
        for match in re.finditer(pattern, title, re.I):
            if not any(a <= match.start() and match.end() <= b for a,b,_ in spans):
                spans.append((match.start(), match.end(), alias))
    return spans


def parse_identity(title, known_titles=()):
    # Reuse primitive season/range grammar, not the retired first-number parser.
    from release_identity import (ReleaseIdentity, Confidence, EpisodeKind,
        _season_from_title, _covered_seasons_from_title, _episode_range_from_title,
        _SPECIAL_PATTERNS, _BATCH_PATTERN, _TECHNICAL_NUMBER_PATTERNS)
    normalized = unicodedata.normalize('NFKC', title)
    spans = title_spans(normalized, known_titles or TITLE_CONTEXT.get())
    masked = list(normalized)
    evidence = []
    for start,end,alias in spans:
        masked[start:end] = ' ' * (end-start)
        evidence.append({'field':'title', 'span':[start,end], 'value':alias, 'basis':'verified_alias'})
    text = ''.join(masked)
    season, season_conf, season_span = _season_from_title(text)
    alias_seasons = {s for _,_,alias in spans for s,c,_ in [_season_from_title(alias)]
                     if s is not None and c is Confidence.EXPLICIT}
    season_conflict = bool(season is not None and alias_seasons and alias_seasons != {season})
    if season is None and len(alias_seasons) == 1:
        season, season_conf = next(iter(alias_seasons)), Confidence.EXPLICIT
        evidence.append({'field':'season','value':season,'basis':'verified_season_title'})
    covered = _covered_seasons_from_title(text, season)
    start_ep, end_ep, range_conf = _episode_range_from_title(text)
    # Alternate absolute numbering in [13 - 总第79] is not a batch.
    local_label = re.search(r'[\[【](\d+(?:\.\d+)?)\s*-\s*(?:总第|總第)\s*\d+\s*[\]】]', text)
    special_markers = tuple(name for name,p in _SPECIAL_PATTERNS.items() if re.search(p,text,re.I))
    media = re.search(r'(?<!\w)(?:PV|OP|ED|trailer|preview|movie|film)(?!\w)|劇場版|剧场版|予告',text,re.I)
    if media:
        special_markers += ('non_regular_media',)
    candidates = []
    if season_span:
        m = re.match(r'\s+(\d+(?:\.\d+)?)(?:v\d+)?(?=\s*(?:SP\d|[\[\(]|$))',text[season_span[1]:],re.I)
        if m:
            candidates.append((Decimal(m.group(1)),'season_suffix',(season_span[1]+m.start(1),season_span[1]+m.end(1))))
    patterns = [
        ('explicit_episode',r'(?<![a-z0-9])s\d+\s*e(?:p(?:isode)?)?\s*0*(\d+(?:\.\d+)?)(?:v\d+)?(?![a-z0-9])'),
        ('explicit_episode',r'(?<![a-z0-9])\d{1,2}x0*(\d+(?:\.\d+)?)(?!\d)'),
        ('explicit_episode',r'(?<![a-z0-9])(?:episode|ep|e)\s*0*(\d+(?:\.\d+)?)(?:v\d+)?(?![a-z0-9])'),
        ('explicit_episode',r'第\s*(\d+(?:\.\d+)?)\s*[话話集]'),
        ('episode_slot',r'\s[-–—]\s*0*(\d+(?:\.\d+)?)(?:v\d+)?(?=\s*(?:[\[\(【]|\.(?:mkv|mp4|ts|avi)$|$))'),
        ('bracket_episode',r'[\[【]\s*0*(\d+(?:\.\d+)?)(?:v\d+)?\s*[\]】]'),
    ]
    if local_label:
        candidates.append((Decimal(local_label.group(1)), 'local_and_absolute_label', local_label.span(1)))
    else:
        for basis,pattern in patterns:
            for m in re.finditer(pattern,text,re.I):
                candidates.append((Decimal(m.group(1)),basis,m.span(1)))
    technical = [m.span() for p in _TECHNICAL_NUMBER_PATTERNS for m in p.finditer(text)]
    technical.extend(m.span() for m in re.finditer(r'\[(?:480|576|720|1080|2160|(?:19|20)\d{2}|\d{8})\]',text))
    candidates = [c for c in candidates if not any(a <= c[2][0] < b for a,b in technical)]
    # A bare numeric token is accepted only in the suffix after the known title.
    if not candidates and spans:
        end = max(b for _,b,_ in spans)
        m = re.match(r'[\s_\]\)【】/:-]*(\d+(?:\.\d+)?)(?:v\d+)?(?=\s*(?:[\[\(【]|\.(?:mkv|mp4|ts)$|$))',text[end:])
        if m:
            candidates.append((Decimal(m.group(1)),'verified_title_suffix',(end+m.start(1),end+m.end(1))))
    parsed = library_parse(normalized)
    series = parsed.get('series', [])
    library_numbers = {Decimal(str(e['number'])) for s in series for e in s.get('episode',[]) if e.get('number') is not None}
    evidence.append({'field':'parser', 'basis':'aniparse-2.0.0', 'episodes': sorted(map(str,library_numbers)),
                     'titles':[s.get('title') for s in series], 'score':parsed.get('_confidence')})
    # Independent structural numbers outrank parser guesses inside title spans.
    strong = {v for v,_,_ in candidates}
    conflicts = []
    if season_conflict or len(alias_seasons)>1:
        conflicts.append('season_title_marker_conflict')
    if len(strong)>1:
        conflicts.append('conflicting_episode_spans')
    episode = next(iter(strong)) if len(strong)==1 else None
    confidence = Confidence.EXPLICIT if episode is not None else Confidence.UNKNOWN
    if not candidates and len(library_numbers)==1:
        value = next(iter(library_numbers))
        occurrences = [m for m in re.finditer(r'(?<![\w.])'+re.escape(str(value))+r'(?![\w.])',text)
                       if not any(a<=m.start()<b for a,b in technical)]
        if occurrences:
            episode,confidence = value,Confidence.WEAK
    for value,basis,span in candidates:
        evidence.append({'field':'episode','value':str(value),'span':list(span),'basis':basis})
    if episode is not None and episode != episode.to_integral_value():
        special_markers += ('decimal_episode',)
    if episode is not None and episode <= 0:
        special_markers += ('nonpositive_episode',)
    batch = start_ep is not None or len(covered)>1 or bool(_BATCH_PATTERN.search(text))
    if batch:
        kind,episode,confidence = EpisodeKind.BATCH,None,Confidence.UNKNOWN
    elif special_markers:
        kind = EpisodeKind.SPECIAL
    elif episode is not None:
        kind = EpisodeKind.REGULAR
    elif season is not None and season_conf is Confidence.EXPLICIT and not conflicts:
        kind = EpisodeKind.BATCH
    else:
        kind = EpisodeKind.UNKNOWN
    decision = IdentityDecision('conflict' if conflicts else ('confirmed' if confidence is Confidence.EXPLICIT else 'unresolved'),
                                str(episode) if episode is not None else None,season,evidence,conflicts)
    decision.kind = kind.value
    if kind is not EpisodeKind.REGULAR:
        decision.evidence.append({'field':'kind','value':kind.value,'basis':'release_structure'})
    return ReleaseIdentity(title,season,season_conf,episode,confidence,kind,special_markers,
                           start_ep,end_ep,covered,range_conf,decision.as_dict())
