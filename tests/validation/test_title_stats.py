"""Validation of title analytics (Tiers 1 and 2): TMDB box office, budget, runtime and ratings vs Wikidata.

Run after collection:  .venv\\Scripts\\python.exe -m pytest -m validation
Collect with:          .venv\\Scripts\\python.exe -m src.source_data_collection.collect_title_stats
"""

from datetime import date

import pytest

from src.processing.build_titles import RELEASE_ORDER_PATH
from src.source_data_collection.collect_title_stats import (
    P_BOX_OFFICE, P_COST, P_DURATION, Q_MINUTE, Q_US_DOLLAR, TMDB_STATS_PATH, WIKIDATA_MONEY_PATH,
)
from src.source_data_collection.storage import read_csv
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.title_types import MOVIE_TYPES
from src.utils import WikimediaClient, label

pytestmark = pytest.mark.validation

TODAY = date(2026, 11, 18)
MIN_RELEASED_FILMS_WITH_BOX_OFFICE = 0.95
MIN_BOX_OFFICE_AGREEMENT, BOX_OFFICE_TOLERANCE = 0.80, 0.10
MIN_BUDGET_AGREEMENT, BUDGET_TOLERANCE = 0.70, 0.25
MIN_RUNTIME_AGREEMENT, RUNTIME_TOLERANCE_MINUTES = 0.90, 3
ENDGAME, DEADPOOL_AND_WOLVERINE = "Q23781155", "Q102180106"


def _load(path):
    if not path.exists():
        pytest.skip(f"{path} not collected yet; run src.source_data_collection.collect_title_stats")
    return read_csv(path)


@pytest.fixture(scope="module")
def stats():
    return {r["title_qid"]: r for r in _load(TMDB_STATS_PATH)}


@pytest.fixture(scope="module")
def money(stats):
    return {r["title_qid"]: r for r in _load(WIKIDATA_MONEY_PATH)}


@pytest.fixture(scope="module")
def released(stats):
    """Titles whose first release is before today (Avengers: Doomsday is not)."""
    return {r["title_qid"] for r in read_csv(RELEASE_ORDER_PATH)
            if date.fromisoformat(r["first_release_date"]) <= TODAY}


def number(value):
    return float(value) if value not in ("", None) else None


def share(passed, total):
    return passed / total if total else 0.0


def agreement(stats, money, tmdb_field, wikidata_field, within):
    pairs = [(q, number(s[tmdb_field]), number(money[q][wikidata_field])) for q, s in stats.items()
             if number(s[tmdb_field]) and number(money[q][wikidata_field])]
    agree = [p for p in pairs if within(p[1], p[2])]
    return share(len(agree), len(pairs)), [p for p in pairs if p not in agree]


# --- Coverage -------------------------------------------------------------------------

def test_released_films_have_box_office(stats, released):
    films = [q for q, s in stats.items() if s["type"] == "Film" and q in released]
    assert share(sum(bool(stats[q]["revenue_usd"]) for q in films), len(films)) >= \
        MIN_RELEASED_FILMS_WITH_BOX_OFFICE


def test_released_titles_have_a_rating_and_genres(stats, released):
    assert [s["title"] for q, s in stats.items() if q in released and not (
        number(s["vote_count"]) and 0 <= number(s["vote_average"]) <= 10 and s["genres"])] == []


# --- TMDB vs Wikidata ------------------------------------------------------------------

def test_box_office_agrees_with_wikidata(stats, money):
    rate, off = agreement(stats, money, "revenue_usd", "box_office_usd",
                          lambda a, b: abs(a - b) <= BOX_OFFICE_TOLERANCE * max(a, b))
    assert rate >= MIN_BOX_OFFICE_AGREEMENT, off


def test_budget_agrees_with_wikidata(stats, money):
    rate, off = agreement(stats, money, "budget_usd", "cost_usd",
                          lambda a, b: abs(a - b) <= BUDGET_TOLERANCE * max(a, b))
    assert rate >= MIN_BUDGET_AGREEMENT, off


def test_runtime_agrees_with_wikidata(stats, money):
    films = {q: s for q, s in stats.items() if s["type"] in MOVIE_TYPES}
    rate, off = agreement(films, money, "runtime_minutes", "duration_minutes",
                          lambda a, b: abs(a - b) <= RUNTIME_TOLERANCE_MINUTES)
    assert rate >= MIN_RUNTIME_AGREEMENT, off


# --- Spot checks -------------------------------------------------------------------------

def test_endgame_is_the_highest_grossing_title_at_about_2_8_billion(stats, money):
    top = max((q for q, s in stats.items() if s["revenue_usd"]), key=lambda q: number(stats[q]["revenue_usd"]))
    assert top == ENDGAME
    assert 2.6e9 <= number(stats[ENDGAME]["revenue_usd"]) <= 3.0e9
    assert 2.6e9 <= number(money[ENDGAME]["box_office_usd"]) <= 3.0e9


def test_deadpool_and_wolverine_passed_a_billion(stats):
    assert number(stats[DEADPOOL_AND_WOLVERINE]["revenue_usd"]) > 1e9


# --- Provenance and IDs -----------------------------------------------------------------

def test_raw_details_were_saved_for_every_title(stats):
    folder = PROJECT_ROOT / "source_data" / "tmdb" / "title_details"
    assert sorted(q for q in stats if not (folder / f"{q}.json").exists()) == []


def test_rows_have_provenance(stats, money):
    rows = list(stats.values()) + list(money.values())
    assert [r["title"] for r in rows for f in ("source", "source_url", "retrieved_at", "license") if not r[f]] == []


def test_property_and_unit_ids_have_expected_labels():
    # P2130 is labelled "capital cost"; the budget agreement check above shows these film items
    # use it for the production budget.
    expected = {P_BOX_OFFICE: "box office", P_COST: "capital cost", P_DURATION: "duration",
                Q_US_DOLLAR: "United States dollar", Q_MINUTE: "minute"}
    entities = WikimediaClient().get_entities(list(expected), props="labels")
    assert {k: label(entities[k]) for k in expected} == expected
