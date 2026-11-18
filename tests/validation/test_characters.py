"""Cross-source validation of characters (Tiers 1 and 2): Wikidata vs Marvel Database (Fandom) vs TMDB.

Run after collection:  .venv\\Scripts\\python.exe -m pytest -m validation
Collect with:          .venv\\Scripts\\python.exe -m src.source_data_collection.collect_characters
"""

import pytest

from src.source_data_collection.cast_matching import character_matches
from src.source_data_collection.collect_characters import (
    CHARACTERS_PATH, FANDOM_LICENSE, MARVEL_DB_PATH, P_BASED_ON, P_BIRTH_NAME, P_DIFFERENT_FROM,
    P_FANDOM_ARTICLE_ID, P_NARRATIVE_UNIVERSE, P_PERFORMER, P_PSEUDONYM, P_SAME_AS, SELF_QID,
    earth_of, wants_marvel_db_page,
)
from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.storage import read_csv
from src.source_data_collection.tmdb_cast import TMDB_CAST_PATH
from src.source_data_collection.wikidata_cast import PERSON_QIDS_PATH, WIKIDATA_CAST_PATH
from src.utils import WikimediaClient, label

pytestmark = pytest.mark.validation

MIN_WITH_UNIVERSE = 0.95
MIN_WITH_MARVEL_DB_ID = 0.70
MIN_TIER2_WITH_MARVEL_DB_ID = 0.50
MAX_STALE_MARVEL_DB_LINKS = 0.10   # Wikidata links to renamed Marvel Database pages
MIN_UNIVERSE_AGREEMENT = 0.95
MIN_REALITY_AGREEMENT = 0.95
MIN_NAME_AGREEMENT = 0.90
MIN_TOP_BILLED_WITH_CHARACTER = 0.70
TOP_BILLED = 10


def _load(path):
    if not path.exists():
        pytest.skip(f"{path} not collected yet; run src.source_data_collection.collect_characters")
    return read_csv(path)


@pytest.fixture(scope="module")
def characters():
    return {r["character_qid"]: r for r in _load(CHARACTERS_PATH)}


@pytest.fixture(scope="module")
def marvel_db(characters):
    return {r["character_qid"]: r for r in _load(MARVEL_DB_PATH)}


def split(value):
    return [v for v in value.split("|") if v]


def wikidata_names(row):
    return [row["label"], *split(row["aliases"]), *split(row["pseudonyms"]), *split(row["birth_names"])]


def marvel_db_names(row):
    return [row["name"], row["current_alias"], *split(row["other_names"])]


def share(passed, total):
    return passed / total if total else 0.0


# --- Wikidata: every cast character is described -----------------------------------------

def test_every_cast_character_was_collected(characters):
    expected = {r["character_qid"] for r in read_csv(WIKIDATA_CAST_PATH)
                if r["character_qid"] and r["character_qid"] != SELF_QID}
    assert sorted(expected - set(characters)) == []


def test_every_character_has_a_label(characters):
    assert [q for q, r in characters.items() if not r["label"]] == []


def test_almost_every_character_has_a_universe(characters):
    assert share(sum(bool(r["universe_qids"]) for r in characters.values()),
                 len(characters)) >= MIN_WITH_UNIVERSE


def test_no_dc_characters_were_collected(characters):
    """Actors in scope also play DC characters (e.g. Henry Cavill's Superman); those must not be kept."""
    dc_universe = "Q1152150"
    assert [r["label"] for r in characters.values() if dc_universe in split(r["universe_qids"])] == []


# --- Marvel Database: coverage and agreement with Wikidata ------------------------------

@pytest.mark.parametrize("tier, minimum", [("1", MIN_WITH_MARVEL_DB_ID), ("2", MIN_TIER2_WITH_MARVEL_DB_ID)])
def test_most_cast_role_characters_link_to_the_marvel_database(characters, tier, minimum):
    """Measured on cast roles, per tier of the title a character first appears in. Wikidata's
    Fandom links are sparser for newer (Tier 2) characters; that floor was set after measuring 55%.
    Characters found via a performer are only used to link credits by name."""
    tiers = {t["wikidata_qid"]: t["tier"] for t in read_csv(REGISTRY_PATH)}
    first = {}
    for r in read_csv(WIKIDATA_CAST_PATH):
        if r["character_qid"] in characters:
            first[r["character_qid"]] = min(first.get(r["character_qid"], "9"), tiers[r["title_qid"]])
    roles = [characters[q] for q, t in first.items()
             if t == tier and characters[q]["found_via"] == "cast_role"]
    assert share(sum(bool(r["marvel_db_page"]) for r in roles), len(roles)) >= minimum


def test_every_linked_marvel_database_page_was_fetched_or_reported_missing(characters, marvel_db):
    """No silent gaps: each linked screen page has a row, fetched or marked missing by the wiki.
    (Network or server errors stop collection, so a missing page is a stale Wikidata link.)"""
    linked = {q for q, r in characters.items() if wants_marvel_db_page(r["marvel_db_page"])}
    assert sorted(linked - set(marvel_db)) == []


def test_few_wikidata_links_to_the_marvel_database_are_stale(characters, marvel_db):
    """Stale links are renamed pages (e.g. 'May Parker' -> 'Maybelle Parker'); listed for review."""
    linked = [q for q, r in characters.items() if wants_marvel_db_page(r["marvel_db_page"])]
    stale = [marvel_db[q]["page"] for q in linked if marvel_db[q]["fetched"] != "True"]
    assert share(len(stale), len(linked)) <= MAX_STALE_MARVEL_DB_LINKS, stale


def test_universe_agrees_with_marvel_database_earth(characters, marvel_db):
    """The Earth in the Marvel Database page title must be one of the character's
    Wikidata universes (each universe item links its own Marvel Database Earth page)."""
    compared = [(q, earth_of(m["page"]), split(characters[q]["universe_earths"]))
                for q, m in marvel_db.items() if earth_of(m["page"]) and characters[q]["universe_earths"]]
    agree = [c for c in compared if c[1] in c[2]]
    assert share(len(agree), len(compared)) >= MIN_UNIVERSE_AGREEMENT, \
        [c for c in compared if c[1] not in c[2]][:20]


def test_reality_field_agrees_with_page_title(marvel_db):
    compared = [m for m in marvel_db.values() if m["reality"] and earth_of(m["page"])]
    agree = [m for m in compared if earth_of(m["page"]) in m["reality"]]
    assert share(len(agree), len(compared)) >= MIN_REALITY_AGREEMENT


def test_names_agree_between_wikidata_and_marvel_database(characters, marvel_db):
    compared = [(characters[q], m) for q, m in marvel_db.items() if m["revid"]]
    agree = [c for c, m in compared
             if any(character_matches(n, wikidata_names(c)) for n in marvel_db_names(m) if n)]
    assert share(len(agree), len(compared)) >= MIN_NAME_AGREEMENT


# --- TMDB: credited roles can be linked to a character --------------------------------

def test_top_billed_tmdb_credits_link_to_a_wikidata_character():
    """Via (title, actor): TMDB credit -> actor QID -> Wikidata cast row with a character."""
    qids = {}
    for r in read_csv(PERSON_QIDS_PATH):
        qids.setdefault(r["tmdb_person_id"], set()).add(r["actor_qid"])
    with_character = {(r["title_qid"], r["actor_qid"]) for r in read_csv(WIKIDATA_CAST_PATH)
                      if r["character_qid"]}
    top = [r for r in read_csv(TMDB_CAST_PATH) if int(r["billing_order"]) < TOP_BILLED]
    linked = [r for r in top
              if any((r["title_qid"], q) in with_character for q in qids.get(r["tmdb_person_id"], ()))]
    assert share(len(linked), len(top)) >= MIN_TOP_BILLED_WITH_CHARACTER


# --- Spot checks ---------------------------------------------------------------------

def test_mcu_tony_stark(characters, marvel_db):
    tony = characters["Q23894967"]
    assert "Earth-199999" in split(tony["universe_earths"])
    assert "Q180704" in split(tony["based_on_qids"])           # comics Iron Man
    assert marvel_db["Q23894967"]["current_alias"] == "Iron Man"


def test_fox_logan_is_a_separate_variant_of_comics_wolverine(characters, marvel_db):
    logan = characters["Q97275436"]
    assert "Earth-10005" in split(logan["universe_earths"])
    assert "Q186422" in split(logan["based_on_qids"])          # comics Wolverine
    assert marvel_db["Q97275436"]["page"] == "James Howlett (Earth-10005)"


def test_mcu_loki_is_based_on_comics_loki_and_differs_from_sylvie(characters):
    loki = characters["Q24046118"]
    assert "Q1147326" in split(loki["based_on_qids"])
    assert "Sylvie" in split(loki["different_from_labels"])


# --- Provenance and property IDs ----------------------------------------------------------

def test_rows_have_provenance(characters, marvel_db):
    rows = list(characters.values()) + list(marvel_db.values())
    assert [r["character_qid"] for r in rows
            for f in ("source", "source_url", "retrieved_at", "license") if not r[f]] == []
    assert {r["license"] for r in marvel_db.values()} == {FANDOM_LICENSE}


def test_character_property_ids_have_expected_labels():
    expected = {P_NARRATIVE_UNIVERSE: "from narrative universe", P_BASED_ON: "based on",
                P_SAME_AS: "said to be the same as", P_DIFFERENT_FROM: "different from",
                P_FANDOM_ARTICLE_ID: "Fandom article ID", P_PSEUDONYM: "pseudonym",
                P_BIRTH_NAME: "birth name", P_PERFORMER: "performer"}
    entities = WikimediaClient().get_entities(list(expected), props="labels")
    assert {p: label(entities[p]) for p in expected} == expected
