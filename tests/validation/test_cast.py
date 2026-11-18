"""Cross-source validation of the cast data (Tiers 1 and 2) (TMDB vs Wikidata vs Wikipedia).

Run after collection:  .venv\\Scripts\\python.exe -m pytest -m validation
Collect with:          .venv\\Scripts\\python.exe -m src.source_data_collection.collect_cast
"""

import pytest

from src.source_data_collection.build_title_registry import REGISTRY_PATH, SEASON
from src.source_data_collection.cast_matching import character_matches, normalize_name
from src.source_data_collection.storage import read_csv, read_json
from src.source_data_collection.tmdb_cast import (
    TMDB_CAST_PATH, TMDB_PERSON_WIKIDATA_PATH,
)
from src.source_data_collection.wikidata_cast import (
    P_CAST_MEMBER, P_CHARACTER_ROLE, P_TMDB_PERSON_ID, P_VOICE_ACTOR, PERSON_QIDS_PATH,
    WIKIDATA_CAST_PATH,
)
from src.source_data_collection.wikipedia_cast import cast_section_path
from src.utils import WikimediaClient, label

pytestmark = pytest.mark.validation

TOP_BILLED = 10                 # billing positions treated as "main cast"
MIN_TMDB_CAST = 10              # every title should list at least this many people
MIN_CHARACTER_FILLED = 0.95     # share of TMDB rows with a character name
MIN_TOP_BILLED_WITH_QID = 0.90  # top-billed actors mapped to a Wikidata QID
MIN_WIKIDATA_CAST_IN_TMDB = 0.85    # Wikidata cast members also listed by TMDB, per title
MIN_CHARACTER_AGREEMENT = 0.85      # Wikidata character agrees with TMDB character
MIN_TOP_BILLED_IN_WIKIPEDIA = 0.95  # top-billed TMDB actors named in Wikipedia's cast section
MIN_TOP_BILLED_IN_WIKIPEDIA_PER_TITLE = 0.80  # ...and in every single title
PROVENANCE_FIELDS = ["source", "source_url", "retrieved_at", "license"]


def _load(path):
    if not path.exists():
        pytest.skip(f"{path} not collected yet; run src.source_data_collection.collect_cast")
    return read_csv(path)


@pytest.fixture(scope="module")
def titles():
    return _load(REGISTRY_PATH)


@pytest.fixture(scope="module")
def tmdb(titles):
    return _load(TMDB_CAST_PATH)


@pytest.fixture(scope="module")
def wikidata(titles):
    return _load(WIKIDATA_CAST_PATH)


@pytest.fixture(scope="module")
def mapping(tmdb):
    return _load(PERSON_QIDS_PATH)


@pytest.fixture(scope="module")
def qids_by_person(mapping):
    """TMDB person ID -> every actor QID linked to it by Wikidata's TMDB person ID (P4985)."""
    grouped = {}
    for r in mapping:
        grouped.setdefault(r["tmdb_person_id"], set()).add(r["actor_qid"])
    return grouped


@pytest.fixture(scope="module")
def persons_by_qid(mapping):
    grouped = {}
    for r in mapping:
        grouped.setdefault(r["actor_qid"], set()).add(r["tmdb_person_id"])
    return grouped


@pytest.fixture(scope="module")
def tmdb_pointer(tmdb):
    """TMDB person ID -> TMDB's own Wikidata ID (top-billed and ambiguous people)."""
    return {r["tmdb_person_id"]: r["wikidata_id"] for r in _load(TMDB_PERSON_WIKIDATA_PATH)}


@pytest.fixture(scope="module")
def top_billed(tmdb):
    return [r for r in tmdb if int(r["billing_order"]) < TOP_BILLED]


def by_title(rows):
    grouped = {}
    for r in rows:
        grouped.setdefault(r["title_qid"], []).append(r)
    return grouped


def actor_roles(tmdb, title_qid, actor_name):
    return [r["character"] for r in tmdb
            if r["title_qid"] == title_qid and r["actor_name"] == actor_name]


# --- TMDB: completeness -------------------------------------------------------

def test_every_title_has_tmdb_cast(titles, tmdb):
    counts = {qid: len(rows) for qid, rows in by_title(tmdb).items()}
    assert [(t["title"], counts.get(t["wikidata_qid"], 0)) for t in titles
            if counts.get(t["wikidata_qid"], 0) < MIN_TMDB_CAST] == []


def test_every_tmdb_row_has_person_name_and_billing(tmdb):
    assert [r for r in tmdb
            if not (r["tmdb_person_id"] and r["actor_name"] and r["billing_order"])] == []


def test_most_tmdb_rows_name_a_character(tmdb):
    filled = sum(bool(r["character"]) for r in tmdb) / len(tmdb)
    assert filled >= MIN_CHARACTER_FILLED


def test_tmdb_rows_have_provenance(tmdb):
    assert [r["title"] for r in tmdb for f in PROVENANCE_FIELDS if not r[f]] == []


# --- Actor identity: TMDB person -> Wikidata QID, two independent routes ------

def test_top_billed_actors_map_to_wikidata(top_billed, qids_by_person):
    mapped = sum(r["tmdb_person_id"] in qids_by_person for r in top_billed) / len(top_billed)
    assert mapped >= MIN_TOP_BILLED_WITH_QID


def test_tmdb_and_wikidata_agree_on_actor_qids(qids_by_person, tmdb_pointer):
    """TMDB's own wikidata_id must be one of the QIDs Wikidata links to that TMDB person."""
    disagreements = [(person, qid, sorted(qids_by_person[person]))
                     for person, qid in tmdb_pointer.items()
                     if qid and person in qids_by_person and qid not in qids_by_person[person]]
    assert disagreements == []


def test_ambiguous_people_are_resolved_by_tmdb(qids_by_person, tmdb_pointer):
    """A TMDB person linked from several Wikidata items needs TMDB's pointer to pick one."""
    unresolved = [(person, sorted(qids)) for person, qids in qids_by_person.items()
                  if len(qids) > 1 and tmdb_pointer.get(person) not in qids]
    assert unresolved == []


# --- Cast membership: Wikidata vs TMDB ----------------------------------------

def test_wikidata_cast_is_listed_by_tmdb(tmdb, wikidata, persons_by_qid):
    """Of the Wikidata cast linked to a TMDB person, most must be in TMDB's credits.

    Wikidata cast members with no TMDB person ID (mostly bulk-imported extras)
    cannot be compared and are left out.
    """
    tmdb_people = {qid: {r["tmdb_person_id"] for r in rows} for qid, rows in by_title(tmdb).items()}
    own_cast = [r for r in wikidata if not r["via"]]  # parent-series cast spans every season
    low = []
    for title_qid, rows in by_title(own_cast).items():
        linked = {r["actor_qid"] for r in rows if r["actor_qid"] in persons_by_qid}
        if not linked:
            continue
        found = sum(bool(persons_by_qid[a] & tmdb_people[title_qid]) for a in linked)
        if found / len(linked) < MIN_WIKIDATA_CAST_IN_TMDB:
            low.append((title_qid, f"{found}/{len(linked)}"))
    assert low == []


def test_wikidata_characters_agree_with_tmdb(tmdb, wikidata, qids_by_person):
    tmdb_characters = {}
    for r in tmdb:
        for qid in qids_by_person.get(r["tmdb_person_id"], ()):
            tmdb_characters.setdefault((r["title_qid"], qid), []).append(r["character"])
    pairs = [(r, tmdb_characters[(r["title_qid"], r["actor_qid"])]) for r in wikidata
             if r["character_qid"] and (r["title_qid"], r["actor_qid"]) in tmdb_characters]
    agree = sum(any(character_matches(c, r["character_names"].split("|")) for c in chars)
                for r, chars in pairs)
    assert pairs and agree / len(pairs) >= MIN_CHARACTER_AGREEMENT


# --- Cast membership: TMDB vs Wikipedia ---------------------------------------

def test_every_title_has_a_wikipedia_cast_section(titles):
    assert [t["title"] for t in titles if not cast_section_path(t["wikidata_qid"]).exists()] == []


def test_top_billed_actors_are_named_on_wikipedia(titles, top_billed):
    """Wikipedia lists principal cast only, so a title may miss a few TMDB top-10 names
    (e.g. Iron Man: Bill Smitrovich and Sayed Badreya appear nowhere in the article). For a
    series spanning several seasons, TMDB ranks by episode count, so its top 10 includes recurring
    characters Wikipedia lists elsewhere (Netflix Daredevil); those only count overall."""
    texts = {t["wikidata_qid"]: normalize_name(read_json(cast_section_path(t["wikidata_qid"]))["wikitext"])
             for t in titles}
    found = {(r["title_qid"], r["tmdb_person_id"]): normalize_name(r["actor_name"]) in texts[r["title_qid"]]
             for r in top_billed}
    assert sum(found.values()) / len(found) >= MIN_TOP_BILLED_IN_WIKIPEDIA
    multi_season = {t["wikidata_qid"] for t in titles if t["seasons"]}  # see docstring
    low = []
    for title_qid in {t for t, _ in found} - multi_season:
        hits = [v for (t, _), v in found.items() if t == title_qid]
        if sum(hits) / len(hits) < MIN_TOP_BILLED_IN_WIKIPEDIA_PER_TITLE:
            low.append((title_qid, f"{sum(hits)}/{len(hits)}"))
    assert low == []


# --- Spot checks (known facts) --------------------------------------------------

@pytest.mark.parametrize("title_qid, actor, character", [
    ("Q192724", "Robert Downey Jr.", "Tony Stark"),           # Iron Man
    ("Q113244839", "Robert Downey Jr.", "Doom"),              # Avengers: Doomsday
    ("Q106182", "Hugh Jackman", "Logan"),                     # X-Men (2000)
    ("Q102180106", "Hugh Jackman", "Logan"),                  # Deadpool & Wolverine
    ("Q107185252", "Tom Hiddleston", "Loki"),                 # Loki, season 1
    ("Q112610403", "Tom Hiddleston", "Loki"),                 # Loki, season 2
    ("Q65980671", "Jeffrey Wright", "The Watcher"),           # What If...?
    ("Q23780734", "Chadwick Boseman", "T'Challa"),            # Black Panther
    ("Q105105219", "Pedro Pascal", "Reed Richards"),          # The Fantastic Four: First Steps
])
def test_known_roles(tmdb, title_qid, actor, character):
    assert any(character in c for c in actor_roles(tmdb, title_qid, actor))


def test_cast_property_ids_have_expected_labels():
    expected = {P_CAST_MEMBER: "cast member", P_VOICE_ACTOR: "voice actor",
                P_CHARACTER_ROLE: "character role", P_TMDB_PERSON_ID: "TMDB person ID"}
    entities = WikimediaClient().get_entities(list(expected), props="labels")
    assert {pid: label(entities[pid]) for pid in expected} == expected


def test_what_if_credits_come_from_seasons_one_and_two_only(tmdb):
    urls = {r["source_url"] for r in tmdb if r["title_qid"] == "Q65980671"}
    assert {u.rsplit("/season/", 1)[1].split("/")[0] for u in urls} == {"1", "2"}


def test_seasons_are_collected_per_season(tmdb, titles):
    """Season rows must come from season credits, not the whole series."""
    seasons = {t["wikidata_qid"] for t in titles if t["type"] == SEASON}
    urls = {r["source_url"] for r in tmdb if r["title_qid"] in seasons}
    assert urls and all("/season/" in u for u in urls)
