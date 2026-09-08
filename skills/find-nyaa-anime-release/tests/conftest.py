"""Offline tests must not silently consult live Nyaa when a mock is missing."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import search_nyaa_releases as nyaa


@pytest.fixture(autouse=True)
def block_unintended_nyaa_transport(request,monkeypatch):
    if request.node.get_closest_marker('live'):
        return
    def blocked(*_,**__):
        pytest.fail('Unmocked live Nyaa transport attempted by an offline test')
    monkeypatch.setattr(nyaa._TRANSPORT_CLIENT,'_request',blocked)
