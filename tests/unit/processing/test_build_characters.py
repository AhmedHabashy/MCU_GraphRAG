"""Unit tests for src/processing/build_characters.py."""

from src.processing.build_characters import (
    MULTIVERSE,
    character_rows,
    link_tmdb_credits,
    own_realities,
    performance_reality,
    resolve_actor,
    wikidata_performances,
)

# --- fixtures -------------------------------------------------------------------------

LOGAN = {"character_qid": "Q97275436", "label": "Logan", "aliases": "James Howlett|Wolverine",
         "pseudonyms": "", "birth_names": "",
         "universe_qids": "Q57317071|Q57317076",
         "universe_earths": "Earth-10005|Earth-TRN414|Earth-17315",
         "based_on_qids": "Q186422", "based_on_labels": "Wolverine",
         "same_as_qids": "", "different_from_qids": "", "different_from_labels": ""}
MAGNETO = {"character_qid": "Q192837", "label": "Magneto", "aliases": "Erik Lehnsherr",
           "pseudonyms": "", "birth_names": "Max Eisenhardt", "universe_qids": "Q2246088",
           "universe_earths": "Earth-616",
           "based_on_qids": "", "based_on_labels": "",
           "same_as_qids": "", "different_from_qids": "", "different_from_labels": ""}
LOKI = {"character_qid": "Q24046118", "label": "Loki", "aliases": "Loki Laufeyson",
        "pseudonyms": "", "birth_names": "", "universe_qids": "Q642878",
        "universe_earths": "Earth-199999",
        "based_on_qids": "Q1147326", "based_on_labels": "Loki",
        "same_as_qids": "", "different_from_qids": "Q107723311", "different_from_labels": "Sylvie"}
CHARACTERS = {c["character_qid"]: c for c in (LOGAN, MAGNETO, LOKI)}
MARVEL_DB = {"Q97275436": {"page": "James Howlett (Earth-10005)", "fetched": "True",
                           "name": "James Howlett", "current_alias": "Wolverine",
                           "other_names": "Weapon X|Jimmy"}}
RELATED = {"Q186422": {"labels": {"en": {"value": "Wolverine"}},
                       "aliases": {"en": [{"value": "Logan"}]}},
           "Q1147326": {"labels": {"en": {"value": "Loki"}}, "aliases": {}}}
TITLES = {"Q106182": {"wikidata_qid": "Q106182", "reality": "Earth-10005"},
          "Q102180106": {"wikidata_qid": "Q102180106", "reality": "Earth-10005"},
          "Q109558622": {"wikidata_qid": "Q109558622", "reality": "Earth-92131"},
          "Q107185252": {"wikidata_qid": "Q107185252", "reality": "Earth-199999"},
          "Q65980671": {"wikidata_qid": "Q65980671", "reality": MULTIVERSE}}
UNIVERSE_EARTHS = {"Q642878": "Earth-199999", "Q2246088": "Earth-616", "Q57317071": "Earth-10005",
                   "Q57317076": "Earth-17315", "Q63728626": "Earth-96283"}


# --- resolve_actor ----------------------------------------------------------------------

def test_resolve_actor_uses_the_only_qid_or_tmdbs_pointer_when_ambiguous():
    qids = {"1": {"Q1"}, "2": {"Q2", "Q3"}, "4": {"Q4", "Q5"}}
    pointer = {"2": "Q3", "4": "Q9"}
    assert resolve_actor("1", qids, pointer) == "Q1"
    assert resolve_actor("2", qids, pointer) == "Q3"
    assert resolve_actor("4", qids, pointer) is None      # pointer not among candidates
    assert resolve_actor("7", qids, pointer) is None


# --- own_realities / performance_reality ---------------------------------------------------

def test_own_realities_use_specific_universes_and_the_marvel_database_earth():
    logan = {"universe_qids": "Q57317071|Q57317076"}
    assert own_realities(logan, UNIVERSE_EARTHS, "Earth-10005") == {"Earth-10005", "Earth-17315"}


def test_franchise_mcu_and_comics_universes_are_not_own_realities():
    """Wikidata's 'Marvel Cinematic Universe' is the whole franchise, not Earth-199999."""
    reed = {"universe_qids": "Q642878"}
    assert own_realities(reed, UNIVERSE_EARTHS, "") == set()
    magneto = {"universe_qids": "Q2246088"}
    assert own_realities(magneto, UNIVERSE_EARTHS, "") == set()


def test_role_without_own_reality_takes_the_title_reality():
    assert performance_reality("Earth-828", set()) == "Earth-828"


def test_role_keeps_title_reality_when_it_is_one_of_its_own():
    assert performance_reality("Earth-10005", {"Earth-10005", "Earth-17315"}) == "Earth-10005"


def test_crossover_role_keeps_its_single_own_reality():
    assert performance_reality("Earth-199999", {"Earth-96283"}) == "Earth-96283"


def test_role_with_several_other_realities_takes_the_title_reality():
    assert performance_reality("Earth-199999", {"Earth-10005", "Earth-17315"}) == "Earth-199999"


def test_anthology_title_makes_every_role_a_multiverse_variant():
    assert performance_reality(MULTIVERSE, {"Earth-199999"}) == MULTIVERSE


# --- wikidata_performances ----------------------------------------------------------------

def test_wikidata_performances_assign_character_ids_per_reality():
    cast = [{"title_qid": "Q106182", "actor_qid": "Q129591", "actor_label": "Ian McKellen",
             "character_qid": "Q192837"},
            {"title_qid": "Q106182", "actor_qid": "Q1", "actor_label": "Self",
             "character_qid": "Q18086706"},                       # 'self' roles skipped
            {"title_qid": "Q106182", "actor_qid": "Q2", "actor_label": "Extra",
             "character_qid": ""}]                                # no character skipped

    rows = wikidata_performances(cast, TITLES, CHARACTERS, MARVEL_DB, UNIVERSE_EARTHS)

    assert [(r["title_qid"], r["actor_name"], r["character_id"], r["source"]) for r in rows] == [
        ("Q106182", "Ian McKellen", "Q192837@Earth-10005", "wikidata")]


# --- link_tmdb_credits -------------------------------------------------------------------

def tmdb(title_qid, person, actor, character):
    return {"title_qid": title_qid, "tmdb_person_id": person, "actor_name": actor,
            "character": character, "billing_order": "0"}


WD_PERFS = [
    {"title_qid": "Q106182", "actor_qid": "QHJ", "actor_name": "Hugh Jackman",
     "base_qid": "Q97275436", "character_id": "Q97275436@Earth-10005"},
    {"title_qid": "Q1000", "actor_qid": "QTH", "actor_name": "Tom Hiddleston",
     "base_qid": "Q24046118", "character_id": "Q24046118@Earth-199999"},
    {"title_qid": "Q2000", "actor_qid": "QX", "actor_name": "Two Roles",
     "base_qid": "Q97275436", "character_id": "Q97275436@Earth-10005"},
    {"title_qid": "Q2000", "actor_qid": "QX", "actor_name": "Two Roles",
     "base_qid": "Q24046118", "character_id": "Q24046118@Earth-199999"},
]
QIDS = {"10": {"QHJ"}, "20": {"QTH"}, "30": {"QX"}, "40": {"QNEW"}}


def link(credit):
    titles = {**TITLES, "Q2000": {"wikidata_qid": "Q2000", "reality": "Earth-199999"}}
    return link_tmdb_credits([credit], WD_PERFS, QIDS, {}, titles, CHARACTERS, MARVEL_DB,
                             UNIVERSE_EARTHS)[0]


def test_tmdb_credit_links_to_the_actors_only_role_in_that_title():
    row = link(tmdb("Q106182", "10", "Hugh Jackman", "Logan / Wolverine"))
    assert row["character_id"] == "Q97275436@Earth-10005" and row["link_method"] == "same_title"
    assert row["tmdb_character"] == "Logan / Wolverine" and row["source"] == "tmdb"


def test_tmdb_credit_for_an_actor_with_two_roles_is_picked_by_name():
    row = link(tmdb("Q2000", "30", "Two Roles", "Loki"))
    assert row["character_id"] == "Q24046118@Earth-199999" and row["link_method"] == "same_title_name"


def test_tmdb_credit_with_no_wikidata_role_uses_the_actors_role_elsewhere_by_name():
    row = link(tmdb("Q107185252", "20", "Tom Hiddleston", "Loki"))        # Loki, season 1
    assert row["character_id"] == "Q24046118@Earth-199999"
    assert row["link_method"] == "other_title_name"


def test_unmatched_tmdb_credit_stays_unlinked():
    row = link(tmdb("Q107185252", "40", "New Actor", "Mobius"))
    assert row["character_id"] == "" and row["link_method"] == ""


# --- character_rows: characters, aliases, links -------------------------------------------

def test_character_rows_build_characters_aliases_and_links():
    perfs = [
        {"title_qid": "Q106182", "base_qid": "Q192837", "character_id": "Q192837@Earth-10005",
         "tmdb_character": "", "source": "wikidata"},
        {"title_qid": "Q106182", "base_qid": "Q192837", "character_id": "Q192837@Earth-10005",
         "tmdb_character": "Erik Lehnsherr / Magneto (uncredited)", "source": "tmdb"},
        {"title_qid": "Q106182", "base_qid": "Q97275436", "character_id": "Q97275436@Earth-10005",
         "tmdb_character": "", "source": "wikidata"},
        {"title_qid": "Q107185252", "base_qid": "Q24046118", "character_id": "Q24046118@Earth-199999",
         "tmdb_character": "", "source": "wikidata"},
    ]
    related = {**RELATED, "Q192837": {"labels": {"en": {"value": "Magneto"}}, "aliases": {}}}

    characters, aliases, links = character_rows(perfs, CHARACTERS, MARVEL_DB, related)

    by_id = {c["character_id"]: c for c in characters}
    assert set(by_id) == {"Q192837@Earth-10005", "Q97275436@Earth-10005", "Q24046118@Earth-199999",
                          "Q192837@Earth-616", "Q186422@Earth-616", "Q1147326@Earth-616"}
    assert by_id["Q186422@Earth-616"]["is_comics_original"] is True
    assert by_id["Q97275436@Earth-10005"]["marvel_db_page"] == "James Howlett (Earth-10005)"

    magneto = {(a["normalized"], a["source"]) for a in aliases if a["character_id"] == "Q192837@Earth-10005"}
    assert {("magneto", "wikidata"), ("erik lehnsherr", "wikidata"), ("max eisenhardt", "wikidata"),
            ("erik lehnsherr", "tmdb"), ("magneto", "tmdb")} <= magneto
    logan = {(a["normalized"], a["source"]) for a in aliases if a["character_id"] == "Q97275436@Earth-10005"}
    assert ("weapon x", "marvel_database") in logan

    relations = {(l["from_id"], l["relation"], l["to_id"], l["to_label"]) for l in links}
    assert ("Q97275436@Earth-10005", "based_on", "Q186422@Earth-616", "Wolverine") in relations
    assert ("Q192837@Earth-10005", "variant_of", "Q192837@Earth-616", "Magneto") in relations
    assert ("Q24046118@Earth-199999", "different_from", "", "Sylvie") in relations
