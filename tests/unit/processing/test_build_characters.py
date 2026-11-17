"""Unit tests for src/processing/build_characters.py (movies and series only; no comics)."""

from src.processing.build_characters import (
    MULTIVERSE,
    Sources,
    character_rows,
    link_tmdb_credits,
    own_realities,
    performance_reality,
    resolve_actor,
    wikidata_roles,
)


def item(qid):
    return {"mainsnak": {"datavalue": {"type": "wikibase-entityid", "value": {"id": qid}}}}


def character(qid, label, aliases="", universes="", based_on="", performers="", mcu_wiki_page="",
              same_as="", different_from="", different_from_labels="", birth_names=""):
    return {"character_qid": qid, "label": label, "aliases": aliases, "pseudonyms": "",
            "birth_names": birth_names, "universe_qids": universes, "based_on_qids": based_on,
            "performer_qids": performers, "mcu_wiki_page": mcu_wiki_page, "same_as_qids": same_as,
            "different_from_qids": different_from, "different_from_labels": different_from_labels}


# --- fixtures -------------------------------------------------------------------------

CHARACTERS = {c["character_qid"]: c for c in [
    character("Q97275436", "Logan", "James Howlett|Wolverine", "Q57317071|Q57317076", "Q186422"),
    character("Q186422", "Wolverine", "Logan", "Q2246088"),
    character("Q192837", "Magneto", "Erik Lehnsherr", "Q2246088", birth_names="Max Eisenhardt"),
    character("Q24046118", "Loki", "Loki Laufeyson", "Q642878", "Q1147326", "QTH", "Loki",
              same_as="Q1147326", different_from="Q107723311|Q1147326",
              different_from_labels="Sylvie|Loki"),
    character("Q107723311", "Sylvie", "", "Q642878", performers="QSDM"),
    character("Q106706981", "Mobius M. Mobius", "Mobius", "Q642878", performers="QOW",
              mcu_wiki_page="Mobius_M._Mobius"),
]}
MARVEL_DB = {"Q97275436": {"page": "James Howlett (Earth-10005)", "fetched": "True",
                           "name": "James Howlett", "current_alias": "Wolverine",
                           "other_names": "Weapon X|Jimmy"},
             "Q24046118": {"page": "Loki Laufeyson (Earth-199999)", "fetched": "True",
                           "name": "Loki Laufeyson", "current_alias": "",
                           "other_names": "God of Mischief"}}
UNIVERSE_PAGES = {"Q642878": "Earth-199999", "Q2246088": "Earth-616", "Q57317071": "Earth-10005",
                  "Q57317076": "Earth-17315", "Q63728626": "Earth-96283"}
RELATED = {"Q107723311": {"labels": {"en": {"value": "Sylvie"}}, "claims": {"P1080": [item("Q642878")]}},
           "Q1147326": {"labels": {"en": {"value": "Loki"}}, "claims": {"P1080": [item("Q2246088")]}}}
TITLES = {"Q106182": {"wikidata_qid": "Q106182", "reality": "Earth-10005"},
          "Q109558622": {"wikidata_qid": "Q109558622", "reality": "Earth-92131"},
          "Q107185252": {"wikidata_qid": "Q107185252", "reality": "Earth-616"},
          "Q65768589": {"wikidata_qid": "Q65768589", "reality": "Earth-616"},
          "Q1000": {"wikidata_qid": "Q1000", "reality": "Earth-616"},
          "Q2000": {"wikidata_qid": "Q2000", "reality": "Earth-616"},
          "Q65980671": {"wikidata_qid": "Q65980671", "reality": MULTIVERSE}}
MCU_CHARACTERS = {"Katy Chen": {"page": "Katy Chen", "real_names": "Katy Chen|Chen Ruiwen",
                                "aliases": "Katy|Little Mooch"},
                  "Mobius M. Mobius": {"page": "Mobius M. Mobius", "real_names": "Mobius M. Mobius",
                                       "aliases": "Mobius"}}
MCU_CREDITS = {("Q65768589", "50", "Katy"): "Katy Chen",
               ("Q107185252", "60", "Agent Mobius"): "Mobius M. Mobius"}


def sources(**overrides):
    values = dict(titles=TITLES, characters=CHARACTERS, marvel_db=MARVEL_DB, related=RELATED,
                  universe_pages=UNIVERSE_PAGES, mcu_credits=MCU_CREDITS,
                  mcu_characters=MCU_CHARACTERS)
    return Sources(**{**values, **overrides})


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
    assert own_realities(CHARACTERS["Q97275436"], UNIVERSE_PAGES, "Earth-10005") == \
        {"Earth-10005", "Earth-17315"}


def test_marvel_database_mcu_page_counts_as_earth_616():
    assert own_realities(CHARACTERS["Q24046118"], UNIVERSE_PAGES, "Earth-199999") == {"Earth-616"}


def test_franchise_mcu_and_comics_universes_are_not_own_realities():
    """Wikidata's 'Marvel Cinematic Universe' is the whole franchise; comics are out of scope."""
    assert own_realities(character("Q1", "X", universes="Q642878"), UNIVERSE_PAGES, "") == set()
    assert own_realities(CHARACTERS["Q192837"], UNIVERSE_PAGES, "Earth-616") == set()


def test_role_without_own_reality_takes_the_title_reality():
    assert performance_reality("Earth-828", set()) == "Earth-828"


def test_role_keeps_title_reality_when_it_is_one_of_its_own():
    assert performance_reality("Earth-10005", {"Earth-10005", "Earth-17315"}) == "Earth-10005"


def test_crossover_role_keeps_its_single_own_reality():
    assert performance_reality("Earth-616", {"Earth-96283"}) == "Earth-96283"


def test_role_with_several_other_realities_takes_the_title_reality():
    assert performance_reality("Earth-616", {"Earth-10005", "Earth-17315"}) == "Earth-616"


def test_anthology_title_makes_every_role_a_multiverse_variant():
    assert performance_reality(MULTIVERSE, {"Earth-616"}) == MULTIVERSE


# --- wikidata_roles -------------------------------------------------------------------------

def cast_row(title, actor_qid, actor, character_qid, via=""):
    return {"title_qid": title, "actor_qid": actor_qid, "actor_label": actor,
            "character_qid": character_qid, "via": via}


def test_wikidata_roles_assign_character_ids_and_keep_their_origin():
    cast = [cast_row("Q106182", "Q129591", "Ian McKellen", "Q192837"),
            cast_row("Q106182", "Q1", "Self", "Q18086706"),               # 'self' roles skipped
            cast_row("Q106182", "Q2", "Extra", ""),                       # no character skipped
            cast_row("Q107185252", "QSDM", "Sophia Di Martino", "Q107723311", "parent_series")]

    rows = wikidata_roles(cast, sources())

    assert [(r["title_qid"], r["actor_name"], r["character_id"], r["via"]) for r in rows] == [
        ("Q106182", "Ian McKellen", "Q192837@Earth-10005", ""),
        ("Q107185252", "Sophia Di Martino", "Q107723311@Earth-616", "parent_series")]


# --- link_tmdb_credits -------------------------------------------------------------------

def tmdb(title_qid, person, actor, character_name):
    return {"title_qid": title_qid, "tmdb_person_id": person, "actor_name": actor,
            "character": character_name, "billing_order": "0"}


ROLES = [
    {"title_qid": "Q106182", "actor_qid": "QHJ", "base_qid": "Q97275436",
     "character_id": "Q97275436@Earth-10005", "via": ""},
    {"title_qid": "Q1000", "actor_qid": "QTH", "base_qid": "Q24046118",
     "character_id": "Q24046118@Earth-616", "via": ""},
    {"title_qid": "Q2000", "actor_qid": "QX", "base_qid": "Q97275436",
     "character_id": "Q97275436@Earth-10005", "via": ""},
    {"title_qid": "Q2000", "actor_qid": "QX", "base_qid": "Q24046118",
     "character_id": "Q24046118@Earth-616", "via": ""},
    {"title_qid": "Q107185252", "actor_qid": "QSDM", "base_qid": "Q107723311",
     "character_id": "Q107723311@Earth-616", "via": "parent_series"},
]
QIDS = {"10": {"QHJ"}, "20": {"QTH"}, "30": {"QX"}, "40": {"QNEW"}, "45": {"QSDM"},
        "55": {"QOW"}, "50": {"QAWK"}, "60": {"QNONE"}}


def link(credit):
    return link_tmdb_credits([credit], ROLES, QIDS, {}, sources())[0]


def test_tmdb_credit_links_to_the_actors_only_role_in_that_title():
    row = link(tmdb("Q106182", "10", "Hugh Jackman", "Logan / Wolverine"))
    assert row["character_id"] == "Q97275436@Earth-10005" and row["link_method"] == "same_title"
    assert row["tmdb_character"] == "Logan / Wolverine" and row["source"] == "tmdb"


def test_season_credit_links_to_the_parent_series_role_even_under_another_name():
    row = link(tmdb("Q107185252", "45", "Sophia Di Martino", "The Variant"))
    assert row["character_id"] == "Q107723311@Earth-616" and row["link_method"] == "parent_series"


def test_tmdb_credit_for_an_actor_with_two_roles_is_picked_by_name():
    row = link(tmdb("Q2000", "30", "Two Roles", "Loki"))
    assert row["character_id"] == "Q24046118@Earth-616" and row["link_method"] == "same_title_name"


def test_tmdb_credit_with_no_wikidata_role_uses_the_actors_role_elsewhere_by_name():
    row = link(tmdb("Q107185252", "20", "Tom Hiddleston", "Loki"))
    assert row["character_id"] == "Q24046118@Earth-616" and row["link_method"] == "other_title_name"


def test_tmdb_credit_links_to_a_character_the_actor_performs_by_name():
    row = link(tmdb("Q107185252", "55", "Owen Wilson", "Mobius"))
    assert row["character_id"] == "Q106706981@Earth-616" and row["link_method"] == "performer"


def test_verified_mcu_wiki_page_of_a_wikidata_character_uses_its_qid():
    row = link(tmdb("Q107185252", "60", "Owen Wilson", "Agent Mobius"))
    assert row["character_id"] == "Q106706981@Earth-616" and row["link_method"] == "mcu_wiki_qid"


def test_verified_mcu_wiki_page_without_a_wikidata_item_becomes_the_identity():
    row = link(tmdb("Q65768589", "50", "Awkwafina", "Katy"))
    assert row["character_id"] == "mcuwiki:Katy_Chen@Earth-616" and row["link_method"] == "mcu_wiki"
    assert row["base_qid"] == "mcuwiki:Katy_Chen"


def test_unmatched_tmdb_credit_stays_unlinked():
    row = link(tmdb("Q107185252", "40", "New Actor", "Hunter X"))
    assert row["character_id"] == "" and row["link_method"] == ""


# --- character_rows: characters, aliases, links -------------------------------------------

def perf(title, base, cid, tmdb_character="", source="wikidata"):
    return {"title_qid": title, "base_qid": base, "character_id": cid,
            "tmdb_character": tmdb_character, "source": source}


PERFS = [
    perf("Q106182", "Q192837", "Q192837@Earth-10005"),                        # Fox Magneto
    perf("Q106182", "Q192837", "Q192837@Earth-10005", "Erik Lehnsherr / Magneto (uncredited)", "tmdb"),
    perf("Q109558622", "Q192837", "Q192837@Earth-92131"),                     # X-Men '97 Magneto
    perf("Q106182", "Q97275436", "Q97275436@Earth-10005"),                    # Fox Logan
    perf("Q109558622", "Q186422", "Q186422@Earth-92131"),                     # X-Men '97 Wolverine
    perf("Q107185252", "Q24046118", "Q24046118@Earth-616"),                   # MCU Loki
    perf("Q107185252", "Q106706981", "Q106706981@Earth-616", "Mobius", "tmdb"),
    perf("Q65768589", "mcuwiki:Katy_Chen", "mcuwiki:Katy_Chen@Earth-616", "Katy", "tmdb"),
]


def build():
    return character_rows(PERFS, sources())


def test_character_rows_contain_only_screen_characters():
    characters, _, _ = build()
    assert {c["character_id"] for c in characters} == {
        "Q192837@Earth-10005", "Q192837@Earth-92131", "Q97275436@Earth-10005",
        "Q186422@Earth-92131", "Q24046118@Earth-616", "Q106706981@Earth-616",
        "mcuwiki:Katy_Chen@Earth-616"}
    assert all("is_comics_original" not in c and "based_on_qids" not in c for c in characters)


def test_mcu_wiki_character_takes_its_name_and_aliases_from_the_wiki():
    characters, aliases, _ = build()
    katy = next(c for c in characters if c["character_id"] == "mcuwiki:Katy_Chen@Earth-616")
    assert katy["label"] == "Katy Chen" and katy["identity_source"] == "mcu_wiki"
    names = {(a["normalized"], a["source"]) for a in aliases if a["character_id"] == katy["character_id"]}
    assert {("katy chen", "mcu_wiki"), ("little mooch", "mcu_wiki"), ("katy", "tmdb")} <= names


def test_wikidata_character_with_a_matched_mcu_wiki_page_also_gets_its_aliases():
    _, aliases, _ = build()
    assert ("Q106706981@Earth-616", "mobius", "mcu_wiki") in {
        (a["character_id"], a["normalized"], a["source"]) for a in aliases}


def test_aliases_pool_wikidata_tmdb_and_matching_marvel_database_names():
    _, aliases, _ = build()
    names = {(a["character_id"], a["normalized"], a["source"]) for a in aliases}
    assert {("Q192837@Earth-10005", "magneto", "wikidata"),
            ("Q192837@Earth-10005", "erik lehnsherr", "wikidata"),
            ("Q192837@Earth-10005", "erik lehnsherr", "tmdb"),
            ("Q97275436@Earth-10005", "weapon x", "marvel_database"),
            ("Q24046118@Earth-616", "god of mischief", "marvel_database")} <= names


def test_screen_variants_are_linked_directly_through_a_shared_item():
    _, _, links = build()
    variants = {(l["from_id"], l["to_id"], l["shared_qid"]) for l in links if l["relation"] == "variant"}
    assert variants == {("Q192837@Earth-10005", "Q192837@Earth-92131", "Q192837"),   # same item
                        ("Q186422@Earth-92131", "Q97275436@Earth-10005", "Q186422")}  # same original


def test_identity_links_keep_screen_targets_and_drop_comics_ones():
    _, _, links = build()
    identity = {(l["from_id"], l["relation"], l["to_label"]) for l in links if l["relation"] != "variant"}
    assert identity == {("Q24046118@Earth-616", "different_from", "Sylvie")}   # comics Loki dropped
