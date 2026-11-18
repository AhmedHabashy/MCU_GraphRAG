"""Validation of MCU wiki matches for TMDB credits (Tiers 1 and 2).

Run after collection:  .venv\\Scripts\\python.exe -m pytest -m validation
Collect with:          .venv\\Scripts\\python.exe -m src.source_data_collection.collect_mcu_wiki
"""

import pytest

from src.source_data_collection.collect_characters import FANDOM_LICENSE
from src.source_data_collection.collect_mcu_wiki import (
    MCU_WIKI_CHARACTERS_PATH, MCU_WIKI_CREDITS_PATH, actor_matches,
)
from src.source_data_collection.storage import read_csv

pytestmark = pytest.mark.validation


def _load(path):
    if not path.exists():
        pytest.skip(f"{path} not collected yet; run src.source_data_collection.collect_mcu_wiki")
    return read_csv(path)


@pytest.fixture(scope="module")
def credits():
    return _load(MCU_WIKI_CREDITS_PATH)


@pytest.fixture(scope="module")
def pages(credits):
    return {r["page"]: r for r in _load(MCU_WIKI_CHARACTERS_PATH)}


def test_every_matched_page_names_the_credited_actor(credits, pages):
    """The actor check is what makes a match trustworthy; re-check it on the saved data."""
    assert [(c["actor_name"], c["tmdb_character"], c["page"]) for c in credits if c["page"]
            and not actor_matches(c["actor_name"], pages[c["page"]]["actors"].split("|"))] == []


def test_every_matched_page_was_saved(credits, pages):
    assert sorted({c["page"] for c in credits if c["page"]} - set(pages)) == []


@pytest.mark.parametrize("actor, character, page", [
    ("Awkwafina", "Katy", "Katy Chen"),
    ("Wunmi Mosaku", "Hunter B-15", "B-15"),
    ("Zawe Ashton", "Dar-Benn", "Dar-Benn"),
    ("Matthew Macfadyen", "Mr. Paradox", "Mr. Paradox"),
    ("Michelle Yeoh", "Ying Nan", "Ying Nan"),
])
def test_known_supporting_characters_are_matched(credits, actor, character, page):
    assert page in {c["page"] for c in credits
                    if c["actor_name"] == actor and c["tmdb_character"] == character}


def test_rows_have_provenance(credits, pages):
    matched = [c for c in credits if c["page"]] + list(pages.values())
    assert [r["page"] for r in matched for f in ("source", "source_url", "retrieved_at") if not r[f]] == []
    assert {r["license"] for r in matched} == {FANDOM_LICENSE}
