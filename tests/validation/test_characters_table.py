"""Validation of the merged character table (one character per reality), aliases and variant links.

Run after building:  .venv\\Scripts\\python.exe -m pytest -m validation
Build with:          .venv\\Scripts\\python.exe -m src.processing.build_characters
"""

from collections import Counter

import pytest

from src.processing.build_characters import (
    ALIASES_PATH, CHARACTERS_PATH, LINKS_PATH, MULTIVERSE, PERFORMANCES_PATH,
)
from src.processing.realities import MCU, marvel_db_page_of, reality_of_marvel_db_earth
from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.cast_matching import normalize_name
from src.source_data_collection.collect_characters import MARVEL_DB_PATH, SELF_QID, earth_of
from src.source_data_collection.storage import read_csv
from src.source_data_collection.tmdb_cast import TMDB_CAST_PATH
from src.source_data_collection.wikidata_cast import WIKIDATA_CAST_PATH
from src.utils import FandomClient

pytestmark = pytest.mark.validation

TOP_BILLED = 10
MIN_TOP_BILLED_LINKED = 0.80
MIN_VOTES_FOR_REALITY_CHECK = 3
MIN_VOTE_SHARE_FOR_REALITY_CHECK = 0.75


def _load(path):
    if not path.exists():
        pytest.skip(f"{path} not built yet; run src.processing.build_characters")
    return read_csv(path)


@pytest.fixture(scope="module")
def characters():
    return {r["character_id"]: r for r in _load(CHARACTERS_PATH)}


@pytest.fixture(scope="module")
def aliases(characters):
    grouped = {}
    for r in _load(ALIASES_PATH):
        grouped.setdefault(r["character_id"], []).append(r)
    return grouped


@pytest.fixture(scope="module")
def links(characters):
    return _load(LINKS_PATH)


@pytest.fixture(scope="module")
def performances(characters):
    return _load(PERFORMANCES_PATH)


@pytest.fixture(scope="module")
def titles():
    return {t["wikidata_qid"]: t for t in read_csv(REGISTRY_PATH)}


def role(performances, title_qid, actor_name):
    """The character_ids an actor (by TMDB or Wikidata name) plays in a title."""
    return {p["character_id"] for p in performances
            if p["title_qid"] == title_qid and p["actor_name"] == actor_name and p["character_id"]}


def names_of(aliases, character_id):
    return {r["normalized"] for r in aliases.get(character_id, [])}


# --- Title realities (curated in docs, checked against data) -----------------------------

def test_every_title_has_a_reality(titles):
    assert [t["title"] for t in titles.values() if not t["reality"]] == []


def test_title_reality_agrees_with_clear_marvel_database_majority(titles):
    """Where the title's characters' Marvel Database pages clearly agree on an Earth, the
    curated reality must match (titles marked for review are skipped)."""
    reality = {r["character_qid"]: reality_of_marvel_db_earth(earth_of(r["page"]))
               for r in read_csv(MARVEL_DB_PATH)}
    cast = read_csv(WIKIDATA_CAST_PATH)
    disagree = []
    for qid, t in titles.items():
        votes = Counter(reality[r["character_qid"]] for r in cast if r["title_qid"] == qid
                        and reality.get(r["character_qid"]))
        if not votes or t["needs_review"] == "True":
            continue
        top, n = votes.most_common(1)[0]
        clear = n >= MIN_VOTES_FOR_REALITY_CHECK and n / sum(votes.values()) >= MIN_VOTE_SHARE_FOR_REALITY_CHECK
        if clear and top != t["reality"]:
            disagree.append((t["title"], t["reality"], dict(votes)))
    assert disagree == []


def _missing_marvel_db_pages(realities):
    client = FandomClient()
    return [r for r in sorted(realities) if client.lead("marvel", marvel_db_page_of(r)) is None]


def test_every_title_reality_is_a_marvel_database_page(titles):
    assert _missing_marvel_db_pages({t["reality"] for t in titles.values()}) == []


def test_every_character_reality_is_a_marvel_database_page(characters):
    """Realities taken from Wikidata universes can be stale (e.g. Earth-TRN414)."""
    assert _missing_marvel_db_pages({c["reality"] for c in characters.values()}) == []


def test_main_mcu_is_earth_616(titles):
    assert titles["Q192724"]["reality"] == MCU                              # Iron Man


# --- Coverage: every role resolves to a character --------------------------------------

def test_every_wikidata_cast_role_has_a_character(performances):
    roles = {(r["title_qid"], r["actor_qid"], r["character_qid"]) for r in read_csv(WIKIDATA_CAST_PATH)
             if r["character_qid"] and r["character_qid"] != SELF_QID}
    resolved = {(p["title_qid"], p["actor_qid"], p["base_qid"]) for p in performances if p["character_id"]}
    assert sorted(roles - resolved)[:20] == []


def test_most_top_billed_tmdb_credits_link_to_a_character(performances):
    top = {(r["title_qid"], r["tmdb_person_id"], r["character"]) for r in read_csv(TMDB_CAST_PATH)
           if int(r["billing_order"]) < TOP_BILLED}
    linked = {(p["title_qid"], p["tmdb_person_id"], p["tmdb_character"]) for p in performances
              if p["character_id"] and p["tmdb_person_id"]}
    assert len(top & linked) / len(top) >= MIN_TOP_BILLED_LINKED


def test_every_performance_character_exists(characters, performances):
    assert sorted({p["character_id"] for p in performances
                   if p["character_id"] and p["character_id"] not in characters}) == []


def test_every_character_has_its_label_as_an_alias(characters, aliases):
    assert [c for c, r in characters.items()
            if normalize_name(r["label"]) not in names_of(aliases, c)] == []


def test_every_alias_names_its_source(aliases):
    sources = {r["source"] for rows in aliases.values() for r in rows}
    assert sources <= {"wikidata", "marvel_database", "tmdb"} and "tmdb" in sources


# --- Acceptance criteria: identity and variants --------------------------------------

def test_magneto_and_erik_lehnsherr_are_one_character(performances, aliases):
    [magneto] = role(performances, "Q106182", "Ian McKellen")             # X-Men (2000)
    assert {"magneto", "erik lehnsherr"} <= names_of(aliases, magneto)


def test_fox_and_animated_wolverines_are_separate_but_linked(performances, characters, links):
    [fox] = role(performances, "Q106182", "Hugh Jackman")                 # X-Men (2000)
    animated = role(performances, "Q109558622", "Cal Dodd")                # X-Men '97
    assert characters[fox]["reality"] == "Earth-10005"
    assert animated and all(characters[a]["reality"] == "Earth-92131" for a in animated)
    assert fox not in animated
    variants = {frozenset((l["from_id"], l["to_id"])) for l in links if l["relation"] == "variant"}
    assert any(frozenset((fox, a)) in variants for a in animated)


def test_crossover_characters_keep_their_own_reality(performances, characters):
    [goblin] = role(performances, "Q68934496", "Willem Dafoe")             # No Way Home
    assert characters[goblin]["reality"] == "Earth-96283"                 # Raimi universe
    [reed] = role(performances, "Q105105219", "Pedro Pascal")              # First Steps
    assert characters[reed]["reality"] == "Earth-828"


def test_what_if_roles_are_multiverse_variants(performances, characters):
    watcher = role(performances, "Q65980671", "Jeffrey Wright")
    assert watcher and all(characters[w]["reality"] == MULTIVERSE for w in watcher)


def test_loki_is_marked_different_from_sylvie(performances, characters, links):
    loki = role(performances, "Q107185252", "Tom Hiddleston")              # Loki, season 1
    assert loki
    assert any(l["relation"] == "different_from" and l["from_id"] in loki
               and l["to_label"] == "Sylvie" for l in links)


def test_no_comics_data_in_the_table(characters, links):
    """Comics are out of scope for now: only screen characters and screen-to-screen links."""
    assert {l["relation"] for l in links} <= {"variant", "same_as", "different_from"}
    assert all(l["to_id"] in characters for l in links if l["relation"] == "variant")
    assert all("is_comics_original" not in c for c in characters.values())


def test_mcu_variants_of_one_character_are_linked(performances, links):
    """MCU Loki and his What If...? multiverse variant share an item, so they are variants."""
    mcu = role(performances, "Q107185252", "Tom Hiddleston")
    variants = {(l["from_id"], l["to_id"]) for l in links if l["relation"] == "variant"}
    assert any(a in mcu or b in mcu for a, b in variants)
