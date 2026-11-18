"""Validation of title details (Tiers 1 and 2): Wikidata cross-checked with TMDB.

Run after collection:  .venv\\Scripts\\python.exe -m pytest -m validation
Collect with:          .venv\\Scripts\\python.exe -m src.source_data_collection.collect_title_details
                       .venv\\Scripts\\python.exe -m src.processing.build_titles
"""

from datetime import date

import pytest

from src.processing.build_titles import RELEASE_ORDER_PATH
from src.source_data_collection.cast_matching import normalize_name
from src.source_data_collection.collect_title_details import (
    ACTOR_BIRTHS_PATH, P_BIRTH_DATE, P_DIRECTOR, P_FOLLOWED_BY, P_FOLLOWS, P_NARRATIVE_LOCATION,
    P_PUBLICATION_DATE, P_SCREENWRITER, TITLE_DETAILS_PATH, TMDB_BIRTHDAYS_PATH, TMDB_CREW_PATH,
    TMDB_FIRST_RELEASES_PATH,
)
from src.source_data_collection.storage import read_csv
from src.source_data_collection.tmdb_cast import TMDB_CAST_PATH, top_billed_person_ids
from src.title_types import MOVIE_TYPES
from src.utils import WikimediaClient, label

pytestmark = pytest.mark.validation

MIN_DIRECTOR_AGREEMENT = 0.95
MIN_FILMS_WITH_WRITER = 0.95
MIN_WRITER_AGREEMENT = 0.80
MAX_RELEASE_WINDOW_DAYS = 21   # premiere to wide release
MIN_ACTORS_WITH_BIRTH_DATE = 0.95
MIN_BIRTH_DATE_AGREEMENT = 0.95


def _load(path):
    if not path.exists():
        pytest.skip(f"{path} not collected yet; run collect_title_details and build_titles")
    return read_csv(path)


@pytest.fixture(scope="module")
def details():
    return {r["title_qid"]: r for r in _load(TITLE_DETAILS_PATH)}


@pytest.fixture(scope="module")
def films(details):
    return [d for d in details.values() if d["type"] in MOVIE_TYPES]


@pytest.fixture(scope="module")
def crew(details):
    grouped = {}
    for r in _load(TMDB_CREW_PATH):
        grouped.setdefault((r["title_qid"], r["role"]), set()).add(normalize_name(r["name"]))
    return grouped


def names(value):
    return {normalize_name(n) for n in value.split("|") if n}


def share(passed, total):
    return passed / total if total else 0.0


# --- Directors and writers: Wikidata vs TMDB crew -----------------------------------------

def test_every_film_has_a_director(films):
    assert [f["title"] for f in films if not f["director_qids"]] == []


def test_directors_agree_with_tmdb(films, crew):
    agree = [f for f in films if names(f["director_names"]) & crew.get((f["title_qid"], "director"), set())]
    assert share(len(agree), len(films)) >= MIN_DIRECTOR_AGREEMENT, \
        [(f["title"], f["director_names"]) for f in films if f not in agree]


def test_most_films_have_a_writer(films):
    assert share(sum(bool(f["writer_qids"]) for f in films), len(films)) >= MIN_FILMS_WITH_WRITER


def test_writers_agree_with_tmdb(films, crew):
    with_writers = [f for f in films if f["writer_names"]]
    agree = [f for f in with_writers if names(f["writer_names"]) & crew.get((f["title_qid"], "writer"), set())]
    assert share(len(agree), len(with_writers)) >= MIN_WRITER_AGREEMENT, \
        [(f["title"], f["writer_names"]) for f in with_writers if f not in agree]


@pytest.mark.parametrize("title_qid, director", [
    ("Q192724", "Jon Favreau"),            # Iron Man
    ("Q23780914", "Joe Russo"),            # Avengers: Infinity War
    ("Q23781155", "Anthony Russo"),        # Avengers: Endgame
    ("Q113244839", "Joe Russo"),           # Avengers: Doomsday
    ("Q106182", "Bryan Singer"),           # X-Men
    ("Q24053263", "James Mangold"),        # Logan
])
def test_known_directors(details, title_qid, director):
    assert normalize_name(director) in names(details[title_qid]["director_names"])


# --- First release dates ------------------------------------------------------------------

def test_every_title_has_a_first_release_date(details):
    assert [d["title"] for d in details.values() if not d["first_release_date"]] == []


def test_wikidata_and_tmdb_dates_fall_in_the_same_release_window(details):
    """The sources record different events of one release (TMDB has most premieres, Wikidata
    mostly theatrical dates), so they differ by days, never by more than the window."""
    tmdb = {r["title_qid"]: r["first_release_date"] for r in _load(TMDB_FIRST_RELEASES_PATH)}
    gaps = [(d["title"], d["first_release_date"], tmdb[q],
             abs((date.fromisoformat(d["first_release_date"]) - date.fromisoformat(tmdb[q])).days))
            for q, d in details.items() if d["first_release_date"] and tmdb.get(q)]
    assert len(gaps) == len(details)
    assert [g for g in gaps if g[3] > MAX_RELEASE_WINDOW_DAYS] == []


def test_first_release_year_matches_the_tier_list_year(order_rows):
    """The tier list's year is the first release year, so the two must agree."""
    from src.source_data_collection.build_title_registry import REGISTRY_PATH
    years = {t["wikidata_qid"]: t["year"] for t in read_csv(REGISTRY_PATH)}
    assert [(r["title"], r["first_release_date"], years[r["title_qid"]]) for r in order_rows
            if r["first_release_date"][:4] != years[r["title_qid"]]] == []


# --- Release order ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def order_rows(details):
    return _load(RELEASE_ORDER_PATH)


@pytest.fixture(scope="module")
def order(order_rows):
    return {r["title_qid"]: int(r["release_order"]) for r in order_rows}


def test_every_title_has_a_release_order(details, order):
    assert sorted(set(details) - set(order)) == []
    assert sorted(order.values()) == list(range(1, len(order) + 1))


def test_release_order_spot_checks(order, details):
    mcu = {q for q, d in details.items() if q not in {
        "Q106182", "Q219776", "Q221168", "Q217552", "Q223596", "Q197491", "Q4985891",
        "Q19347291", "Q17042878", "Q24053263", "Q25431158", "Q31188935", "Q28912376"}}
    assert order["Q106182"] == 1                                          # X-Men (2000) first overall
    assert min(mcu, key=order.get) == "Q192724"                           # Iron Man first in the MCU
    assert max(order, key=order.get) == "Q113244839"                      # Avengers: Doomsday last
    assert order["Q89474225"] < order["Q102180106"]                       # The Marvels < Deadpool & Wolverine
    assert order["Q23781155"] < order["Q27985819"]                        # Endgame < Far From Home


def test_follows_links_point_to_earlier_titles(details, order):
    """Where Wikidata says title A follows title B and both are in scope, B came out first."""
    wrong = [(d["title"], d["follows_names"]) for q, d in details.items()
             for prev in d["follows_qids"].split("|") if prev in order and order[prev] >= order[q]]
    assert wrong == []


@pytest.mark.parametrize("title_qid, previous", [
    ("Q205028", "Q192724"),                # Iron Man 2 follows Iron Man
    ("Q219776", "Q106182"),                # X2 follows X-Men
])
def test_known_sequels(details, title_qid, previous):
    assert previous in details[title_qid]["follows_qids"].split("|")


# --- Actor birth dates ----------------------------------------------------------------------

def test_top_billed_actors_have_birth_dates():
    """Every credited actor is collected; coverage is measured on the top-billed, because many
    minor actors have no published birth date."""
    top = set(top_billed_person_ids(read_csv(TMDB_CAST_PATH)))
    births = [b for b in _load(ACTOR_BIRTHS_PATH) if b["tmdb_person_id"] in top]
    assert share(sum(bool(b["birth_dates"]) for b in births), len(births)) >= MIN_ACTORS_WITH_BIRTH_DATE


def test_birth_dates_were_collected_beyond_the_top_billed():
    top = set(top_billed_person_ids(read_csv(TMDB_CAST_PATH)))
    assert len({b["tmdb_person_id"] for b in _load(ACTOR_BIRTHS_PATH)} - top) > len(top)


def test_birth_dates_agree_with_tmdb():
    """Measured on the top-billed, like coverage: minor actors' birthdays are often wrong in one
    of the sources."""
    top = set(top_billed_person_ids(read_csv(TMDB_CAST_PATH)))
    tmdb = {r["tmdb_person_id"]: r["birthday"] for r in _load(TMDB_BIRTHDAYS_PATH) if r["tmdb_person_id"] in top}
    pairs = [(b["tmdb_person_id"], b["birth_dates"].split("|"), tmdb.get(b["tmdb_person_id"]))
             for b in _load(ACTOR_BIRTHS_PATH) if b["birth_dates"] and tmdb.get(b["tmdb_person_id"])]
    agree = [p for p in pairs if p[2] in p[1]]
    assert share(len(agree), len(pairs)) >= MIN_BIRTH_DATE_AGREEMENT, [p for p in pairs if p not in agree]


def test_robert_downey_jr_birth_date():
    births = {b["actor_qid"]: b["birth_dates"] for b in _load(ACTOR_BIRTHS_PATH)}
    assert "1965-04-04" in births["Q165219"].split("|")


# --- Provenance and property IDs ------------------------------------------------------------

def test_rows_have_provenance(details):
    rows = list(details.values()) + _load(TMDB_FIRST_RELEASES_PATH) + _load(ACTOR_BIRTHS_PATH)
    assert [r for r in rows for f in ("source", "source_url", "retrieved_at", "license") if not r[f]] == []


def test_title_detail_property_ids_have_expected_labels():
    expected = {P_DIRECTOR: "director", P_SCREENWRITER: "screenwriter",
                P_PUBLICATION_DATE: "publication date", P_FOLLOWS: "follows",
                P_FOLLOWED_BY: "followed by", P_NARRATIVE_LOCATION: "narrative location",
                P_BIRTH_DATE: "date of birth"}
    entities = WikimediaClient().get_entities(list(expected), props="labels")
    assert {p: label(entities[p]) for p in expected} == expected
