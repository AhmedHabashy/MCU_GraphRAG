"""Validation of the in-universe timeline: MCU wiki viewing order vs Wikipedia's timeline years.

Run after collection:  .venv\\Scripts\\python.exe -m pytest -m validation
Collect with:          .venv\\Scripts\\python.exe -m src.source_data_collection.collect_timeline
                       .venv\\Scripts\\python.exe -m src.processing.build_titles
"""

from itertools import combinations

import pytest

from src.processing.build_titles import TIMELINE_PATH
from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.collect_timeline import VIEWING_TIMELINE_PATH, WIKIPEDIA_TIMELINE_PATH
from src.source_data_collection.storage import read_csv

pytestmark = pytest.mark.validation

OUTSIDE_MCU_TIMELINE = {"Fox X-Men", "MCU animation"}   # X-Men '97 and other universes' animation
MIN_IN_MCU_WIKI_ORDER = 0.90
MIN_WITH_WIKIPEDIA_YEAR = 0.80
MIN_START_YEAR_AGREEMENT = 0.85
MIN_PAIR_ORDER_AGREEMENT = 0.90


def _load(path):
    if not path.exists():
        pytest.skip(f"{path} not collected yet; run collect_timeline and build_titles")
    return read_csv(path)


@pytest.fixture(scope="module")
def titles():
    return {t["wikidata_qid"]: t for t in read_csv(REGISTRY_PATH)}


@pytest.fixture(scope="module")
def timeline(titles):
    return {r["title_qid"]: r for r in _load(TIMELINE_PATH)}


@pytest.fixture(scope="module")
def mcu(titles):
    """Titles on the main MCU timeline (Fox films and other-universe animation are not)."""
    return [q for q, t in titles.items() if t["universe"] not in OUTSIDE_MCU_TIMELINE
            or t["reality"] == "Earth-616"]


def share(passed, total):
    return passed / total if total else 0.0


def number(value):
    return int(value) if value not in ("", None) else None


def test_most_mcu_titles_are_in_the_viewing_order(timeline, mcu, titles):
    missing = [titles[q]["title"] for q in mcu if timeline[q]["chronological_order"] == ""]
    assert share(len(mcu) - len(missing), len(mcu)) >= MIN_IN_MCU_WIKI_ORDER, missing


def test_most_mcu_titles_have_a_wikipedia_year(timeline, mcu, titles):
    missing = [titles[q]["title"] for q in mcu if timeline[q]["wikipedia_start_year"] == ""]
    assert share(len(mcu) - len(missing), len(mcu)) >= MIN_WITH_WIKIPEDIA_YEAR, missing


def test_start_years_agree_between_the_sources(timeline, titles):
    both = [r for r in timeline.values() if r["mcu_wiki_start_year"] and r["wikipedia_start_year"]]
    off = [(titles[r["title_qid"]]["title"], r["mcu_wiki_start_year"], r["wikipedia_start_year"]) for r in both
           if abs(number(r["mcu_wiki_start_year"]) - number(r["wikipedia_start_year"])) > 1]
    assert share(len(both) - len(off), len(both)) >= MIN_START_YEAR_AGREEMENT, off


def test_the_orders_agree_for_titles_in_different_wikipedia_years(timeline, titles):
    placed = [r for r in timeline.values() if r["chronological_order"] and r["wikipedia_start_year"]]
    pairs = [(a, b) for a, b in combinations(placed, 2)
             if number(a["wikipedia_start_year"]) != number(b["wikipedia_start_year"])]
    agree = [(a, b) for a, b in pairs if (number(a["wikipedia_start_year"]) < number(b["wikipedia_start_year"]))
             == (number(a["chronological_order"]) < number(b["chronological_order"]))]
    assert share(len(agree), len(pairs)) >= MIN_PAIR_ORDER_AGREEMENT


@pytest.mark.parametrize("title_qid, start, end", [
    ("Q275120", 1943, 1945),        # Captain America: The First Avenger (the MCU wiki starts in 1942)
    ("Q23781129", 1995, 1995),      # Captain Marvel
    ("Q192724", 2010, 2010),        # Iron Man
    ("Q23780914", 2018, 2018),      # Avengers: Infinity War
])
def test_known_wikipedia_years(timeline, title_qid, start, end):
    assert (number(timeline[title_qid]["wikipedia_start_year"]),
            number(timeline[title_qid]["wikipedia_end_year"])) == (start, end)


def test_endgame_comes_before_far_from_home(timeline):
    assert number(timeline["Q23781155"]["chronological_order"]) < number(timeline["Q27985819"]["chronological_order"])


def test_fox_films_are_not_on_the_mcu_timeline(timeline, titles):
    assert [t["title"] for q, t in titles.items() if t["universe"] == "Fox X-Men"
            and timeline[q]["chronological_order"] != ""] == []


def test_rows_have_provenance():
    rows = _load(VIEWING_TIMELINE_PATH) + _load(WIKIPEDIA_TIMELINE_PATH)
    assert [r for r in rows for f in ("source", "source_url", "revid", "retrieved_at", "license") if not r[f]] == []
