"""Validation of the merged character table (one character per reality), aliases and variant links.

Run after building:  .venv\\Scripts\\python.exe -m pytest -m validation
Build with:          .venv\\Scripts\\python.exe -m src.processing.build_characters
"""

from collections import Counter

import pytest

from src.processing.build_characters import (
    ALIASES_PATH, CHARACTERS_PATH, LINKS_PATH, MULTIVERSE, PERFORMANCES_PATH,
)
from src.processing.curated_roles import (
    UNKNOWN_REALITY, curated_row, load_curated_roles, load_dropped_roles, unmatched_rows,
)
from src.processing.realities import MCU, marvel_db_page_of, reality_of_marvel_db_earth
from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.cast_matching import normalize_name
from src.source_data_collection.collect_characters import (
    CHARACTERS_PATH as COLLECTED_CHARACTERS_PATH, MARVEL_DB_PATH, SELF_QID, earth_of,
)
from src.source_data_collection.collect_mcu_wiki import MCU_WIKI_CHARACTERS_PATH
from src.source_data_collection.storage import read_csv
from src.source_data_collection.tmdb_cast import TMDB_CAST_PATH
from src.source_data_collection.wikidata_cast import WIKIDATA_CAST_PATH
from src.utils import FandomClient

pytestmark = pytest.mark.validation

TOP_BILLED = 10
MIN_TOP_BILLED_LINKED = 0.90
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
        if not votes or t["needs_review"] == "True" or t["reality"] == MULTIVERSE:
            continue  # an anthology's characters are variants of characters from elsewhere
        top, n = votes.most_common(1)[0]
        clear = n >= MIN_VOTES_FOR_REALITY_CHECK and n / sum(votes.values()) >= MIN_VOTE_SHARE_FOR_REALITY_CHECK
        if clear and top != t["reality"]:
            disagree.append((t["title"], t["reality"], dict(votes)))
    assert disagree == []


def _missing_marvel_db_pages(realities):
    """'Unknown' is the expert's answer for a role from another, unnumbered universe."""
    client = FandomClient()
    return [r for r in sorted(realities - {UNKNOWN_REALITY})
            if client.lead("marvel", marvel_db_page_of(r)) is None]


def test_every_title_reality_is_a_marvel_database_page(titles):
    assert _missing_marvel_db_pages({t["reality"] for t in titles.values()}) == []


def test_every_character_reality_is_a_marvel_database_page(characters):
    """Realities taken from Wikidata universes can be stale (e.g. Earth-TRN414)."""
    assert _missing_marvel_db_pages({c["reality"] for c in characters.values()}) == []


def test_main_mcu_is_earth_616(titles):
    assert titles["Q192724"]["reality"] == MCU                              # Iron Man


# --- Coverage: every role resolves to a character --------------------------------------

def test_every_wikidata_cast_role_has_a_character(performances, titles):
    """Except the roles the expert dropped (docs, "Dropped roles")."""
    qid_of = {t["title"]: q for q, t in titles.items()}
    dropped = {(qid_of[r["title"]], normalize_name(r["actor"])) for r in load_dropped_roles()}
    roles = {(r["title_qid"], r["actor_qid"], r["character_qid"]) for r in read_csv(WIKIDATA_CAST_PATH)
             if r["character_qid"] and r["character_qid"] != SELF_QID and not r["via"]
             and (r["title_qid"], normalize_name(r["actor_label"])) not in dropped}
    resolved = {(p["title_qid"], p["actor_qid"], p["data_base_qid"]) for p in performances
                if p["character_id"]}  # data_base_qid: the role's character before curation
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
    assert sources == {"wikidata", "marvel_database", "tmdb", "mcu_wiki", "curated"}


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


# --- Character gaps: parent-series cast, performer and MCU wiki identities ----------------

LOKI_S1, LOKI_S2 = "Q107185252", "Q112610403"


@pytest.mark.parametrize("actor", ["Sophia Di Martino", "Owen Wilson", "Wunmi Mosaku"])
def test_loki_supporting_characters_are_one_character_across_both_seasons(performances, actor):
    """Sylvie (credited as 'The Variant' in season 1), Mobius and B-15."""
    s1, s2 = role(performances, LOKI_S1, actor), role(performances, LOKI_S2, actor)
    assert len(s1) == 1 and s1 == s2


def test_sylvie_is_linked_through_the_parent_series_cast(performances, characters):
    [sylvie] = role(performances, LOKI_S1, "Sophia Di Martino")
    assert characters[sylvie]["label"] == "Sylvie"


@pytest.mark.parametrize("title_qid, actor", [
    ("Q65768589", "Awkwafina"),            # Katy, Shang-Chi
    ("Q65768589", "Michelle Yeoh"),        # Ying Nan, Shang-Chi
    ("Q89474225", "Zawe Ashton"),          # Dar-Benn, The Marvels
    ("Q102180106", "Matthew Macfadyen"),   # Mr. Paradox, Deadpool & Wolverine
])
def test_supporting_characters_without_wikidata_items_are_linked(performances, title_qid, actor):
    assert role(performances, title_qid, actor)


def test_parent_series_roles_only_count_for_actors_credited_in_that_season(performances):
    """Wikidata's Loki series cast spans both seasons; Ke Huy Quan (OB) is only in season 2."""
    assert not role(performances, LOKI_S1, "Ke Huy Quan")
    assert not [p for p in performances if p["via"]]


def test_mcu_wiki_identity_is_only_used_without_a_wikidata_character(characters):
    collected = {c["mcu_wiki_page"].replace("_", " ")
                 for c in read_csv(COLLECTED_CHARACTERS_PATH) if c["mcu_wiki_page"]}
    assert sorted(c["mcu_wiki_page"] for c in characters.values()
                  if c["identity_source"] == "mcu_wiki" and c["mcu_wiki_page"] in collected) == []


# --- Curated roles (MCU expert) --------------------------------------------------------------

@pytest.fixture(scope="module")
def curated():
    return load_curated_roles()


@pytest.fixture(scope="module")
def title_qids(titles):
    return {t["title"]: q for q, t in titles.items()}


def test_every_curated_title_names_exactly_one_title(curated, titles):
    """Titles are matched by name, and some names repeat (Fantastic Four, 2005 and 2015)."""
    names = Counter(t["title"] for t in titles.values())
    assert [r["title"] for r in curated if r["title"] != "*" and names[r["title"]] != 1] == []


@pytest.fixture(scope="module")
def dropped():
    return load_dropped_roles()


def test_every_dropped_title_names_exactly_one_title(dropped, titles):
    names = Counter(t["title"] for t in titles.values())
    assert [r["title"] for r in dropped if names[r["title"]] != 1] == []


def test_dropped_roles_are_gone(performances, dropped, title_qids):
    """MCU expert, round 3: Saldaña is not Drax in the Holiday Special, W'Kabi is not in
    Wakanda Forever, Jimmy Woo is not in The Marvels."""
    assert [(r["title"], r["actor"]) for r in dropped if role(performances, title_qids[r["title"]], r["actor"])] == []


def test_every_curated_role_matches_a_performance(performances, curated, title_qids):
    assert [(r["title"], r["actor"]) for r in unmatched_rows(performances, curated, title_qids)] == []


def test_every_matching_performance_has_its_curated_identity_and_reality(performances, curated, title_qids):
    wrong = []
    for p in performances:
        r = curated_row(p, curated, title_qids)
        if p["character_id"] and r:
            identity, reality = p["character_id"].rsplit("@", 1)
            if (r["identity"] and identity != r["identity"]) or (r["reality"] and reality != r["reality"]):
                wrong.append((r["title"], r["actor"], p["character_id"]))
    assert wrong == []


@pytest.mark.parametrize("title_qid, reality", [
    ("Q111382701", "Earth-89521"),         # Marvel Zombies
    ("Q113005299", "Earth-86445"),         # Your Friendly Neighborhood Spider-Man
])
def test_titles_set_in_their_own_universe_keep_every_role_there(performances, title_qid, reality):
    """MCU expert, round 2: these characters are local variants, not MCU visitors."""
    assert {p["character_id"].rsplit("@", 1)[1] for p in performances
            if p["title_qid"] == title_qid and p["character_id"]} == {reality}


def test_mcu_visitors_in_deadpool_and_wolverine_stay_in_the_mcu(performances, characters):
    """Deadpool visits the main MCU: its Thor and Happy Hogan are the Earth-616 characters."""
    for actor in ("Chris Hemsworth", "Jon Favreau"):
        assert characters[ids(performances, "Q102180106", actor)]["reality"] == MCU


def ids(performances, title_qid, actor):
    found = role(performances, title_qid, actor)
    assert len(found) == 1, (title_qid, actor, found)
    return next(iter(found))


def test_no_way_home_villains_keep_their_home_realities(performances, characters):
    assert characters[ids(performances, "Q68934496", "Alfred Molina")]["reality"] == "Earth-96283"
    assert characters[ids(performances, "Q68934496", "Jamie Foxx")]["reality"] == "Earth-120703"
    assert characters[ids(performances, "Q68934496", "Rhys Ifans")]["reality"] == "Earth-120703"
    assert characters[ids(performances, "Q68934496", "Thomas Haden Church")]["reality"] == "Earth-96283"


@pytest.mark.parametrize("crossover, home, actor", [
    ("Q68934496", "Q190145", "Alfred Molina"),       # No Way Home / Spider-Man 2: Doc Ock
    ("Q68934496", "Q484442", "Willem Dafoe"),        # No Way Home / Spider-Man: Green Goblin
    ("Q68934496", "Q4254026", "Jamie Foxx"),         # No Way Home / The Amazing Spider-Man 2: Electro
    ("Q68934496", "Q484442", "Tobey Maguire"),       # No Way Home / Spider-Man: Peter Parker
    ("Q102180106", "Q224130", "Chris Evans"),        # Deadpool & Wolverine / Fantastic Four (2005)
])
def test_crossover_roles_are_the_characters_of_their_home_films(performances, crossover, home, actor):
    """MCU expert, round 2: the visitors are the same characters as in their own films."""
    assert ids(performances, crossover, actor) == ids(performances, home, actor)


def test_the_i_am_groot_watcher_is_the_what_if_watcher(performances):
    """MCU expert, round 3."""
    assert ids(performances, "Q108170999", "Jeffrey Wright") == ids(performances, "Q65980671", "Jeffrey Wright")


def test_the_morbius_vulture_is_the_mcu_vulture(performances):
    """MCU expert, round 3: Morbius's Vulture is Spider-Man: Homecoming's, sent to Sony's universe."""
    assert ids(performances, "Q55405369", "Michael Keaton") == ids(performances, "Q23010088", "Michael Keaton")


def test_he_who_remains_and_victor_timely_are_kang_variants(performances, links):
    """MCU expert, round 3: each is a variant of Kang the Conqueror (Quantumania)."""
    kang = ids(performances, "Q105359456", "Jonathan Majors")
    variants = {(l["from_id"], l["to_id"]) for l in links if l["relation"] == "variant"}
    for title_qid, identity in (("Q107185252", "mcuwiki:He_Who_Remains"), ("Q112610403", "mcuwiki:Victor_Timely")):
        cid = ids(performances, title_qid, "Jonathan Majors")
        assert cid.startswith(identity + "@")
        assert (kang, cid) in variants or (cid, kang) in variants


def test_no_way_home_spider_men_each_keep_their_own_universe(performances, characters):
    """MCU expert, round 2: each Spider-Man is from his own Earth."""
    realities = [characters[ids(performances, "Q68934496", a)]["reality"]
                 for a in ("Tom Holland", "Tobey Maguire", "Andrew Garfield")]
    assert realities == [MCU, "Earth-96283", "Earth-120703"]


def test_gambit_is_one_character_in_deadpool_and_wolverine_and_doomsday(performances, characters):
    """MCU expert, round 2: the Doomsday Gambit is the one who escaped the Void."""
    gambit = ids(performances, "Q102180106", "Channing Tatum")
    assert gambit == ids(performances, "Q113244839", "Channing Tatum")
    assert characters[gambit]["reality"] == UNKNOWN_REALITY


@pytest.mark.parametrize("actor, reality", [
    ("Jennifer Garner", "Earth-701306"),   # Elektra (2005)
    ("Wesley Snipes", "Earth-26320"),      # Blade trilogy
    ("Chris Evans", "Earth-121698"),       # Fantastic Four (2005)
    ("Hugh Jackman", UNKNOWN_REALITY),
    ("Henry Cavill", UNKNOWN_REALITY),
])
def test_deadpool_and_wolverine_void_cameos_come_from_their_own_universes(performances, characters,
                                                                           actor, reality):
    assert characters[ids(performances, "Q102180106", actor)]["reality"] == reality


def test_may_parker_is_known_by_both_names(performances, aliases):
    """MCU expert, round 2: May is short for Maybelle, so both names are right."""
    may = ids(performances, "Q68934496", "Marisa Tomei")
    assert {"may parker", "maybelle parker"} <= names_of(aliases, may)


def test_doomsday_crossovers_are_the_same_characters_as_in_their_home_films(performances):
    assert ids(performances, "Q113244839", "Pedro Pascal") == ids(performances, "Q105105219", "Pedro Pascal")
    assert ids(performances, "Q113244839", "Patrick Stewart") == ids(performances, "Q106182", "Patrick Stewart")
    assert ids(performances, "Q89474225", "Kelsey Grammer") == ids(performances, "Q221168", "Kelsey Grammer")


def test_deadpool_and_wolverine_wolverines_are_separate_variants_of_fox_logan(performances, links):
    fox = ids(performances, "Q106182", "Hugh Jackman")
    dw = ids(performances, "Q102180106", "Hugh Jackman")
    cavill = ids(performances, "Q102180106", "Henry Cavill")
    assert len({fox, dw, cavill}) == 3
    variants = {frozenset((l["from_id"], l["to_id"])) for l in links if l["relation"] == "variant"}
    assert frozenset((fox, dw)) in variants and frozenset((fox, cavill)) in variants


def test_captain_carter_is_a_separate_character_from_peggy_carter(performances, characters, links):
    carter = ids(performances, "Q64211112", "Hayley Atwell")         # Multiverse of Madness
    peggy = ids(performances, "Q275120", "Hayley Atwell")            # The First Avenger
    assert carter != peggy
    assert (characters[carter]["label"], characters[carter]["reality"]) == ("Captain Carter", "Earth-838")
    assert characters[peggy]["reality"] == "Earth-616"


def test_friday_is_linked_to_its_own_character(performances, characters):
    assert characters[ids(performances, "Q23010088", "Kerry Condon")]["label"] == "F.R.I.D.A.Y."


def test_damion_poitier_played_thanos(performances, characters):
    assert characters[ids(performances, "Q182218", "Damion Poitier")]["label"] == "Thanos"


def test_yelena_is_one_character_in_black_widow_and_thunderbolts(performances):
    """Wikidata points Thunderbolts* at the comics Yelena and Black Widow at the MCU one."""
    assert ids(performances, "Q23894626", "Florence Pugh") == ids(performances, "Q112322474", "Florence Pugh")


def test_no_reality_keeps_a_comics_role_next_to_its_single_screen_character(performances):
    """After merging, a comics item and the one screen character based on it never share a reality."""
    collected = {c["character_qid"]: c for c in read_csv(COLLECTED_CHARACTERS_PATH)}
    present = {}
    for p in performances:
        if p["character_id"]:
            identity, reality = p["character_id"].rsplit("@", 1)
            present.setdefault(reality, set()).add(identity)
    leftovers = []
    for reality, identities in present.items():
        for identity in identities:
            screen = [s for s in identities if identity in collected.get(s, {}).get("based_on_qids", "").split("|")]
            if len(screen) == 1 and identity in collected and not collected[identity]["universe_qids"].count("Q642878") \
                    and "Q2246088" in collected[identity]["universe_qids"].split("|"):
                leftovers.append((reality, identity, screen[0]))
    assert leftovers == []


def test_video_game_realities_are_not_used(characters):
    assert [c for c, r in characters.items() if r["reality"] == "Earth-30847"] == []


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


# --- species (from the MCU wiki infobox) ----------------------------------------------------

def test_daisy_johnson_is_an_inhuman(characters):
    """Expert, round 4: link the Agents of S.H.I.E.L.D. Daisy Johnson to the Inhumans."""
    assert characters["Q24027972@Earth-616"]["species"] == "Inhuman"


@pytest.mark.parametrize("cid, species", [
    ("Q24046102@Earth-616", "Asgardian"),       # Thor
    ("Q24046118@Earth-616", "Frost Giant"),     # Loki
    ("Q64658380@Earth-616", "Human|Kree"),      # Carol Danvers: "Human/Kree Hybrid"
    ("Q24050072@Earth-616", "Zehoberei"),       # Gamora: "Zehoberei (Cyborg)"
    ("Q64825451@Earth-616", "Titan"),           # Thanos: "[[Titans|Titan]]"
    ("Q23894967@Earth-616", "Human"),           # Tony Stark: page declared by Wikidata only
])
def test_known_species(characters, cid, species):
    assert characters[cid]["species"] == species


def test_species_names_are_clean(characters):
    """No wiki markup, notes or qualifiers left in a species name."""
    names = {s for c in characters.values() for s in c["species"].split("|") if s}
    assert [n for n in names if any(ch in n for ch in "[]{}<>=()") or n.lower() in ("hybrid", "glossary")
            or "formerly" in n.lower() or "temporarily" in n.lower()] == []


def test_species_have_one_form(characters):
    """"Humans" (a link to the plural page) is the same species as "Human"."""
    names = {s for c in characters.values() for s in c["species"].split("|") if s}
    assert [n for n in names if n.endswith("s") and n[:-1] in names] == []


def test_every_character_with_a_species_on_its_mcu_wiki_page_has_it(characters):
    pages = {r["requested_page"]: r for r in read_csv(MCU_WIKI_CHARACTERS_PATH)}
    assert [c["character_id"] for c in characters.values() if not c["species"]
            and pages.get(c["mcu_wiki_page"], {}).get("species")] == []


def test_names_have_no_wiki_markup(characters, aliases):
    """References and comments are dropped before a name list is split (Swoll Groot<ref>...)."""
    markup = ("<ref", "</ref", "<!--", "-->", "{{", "}}", "[[", "]]")
    names = [c["label"] for c in characters.values()] + [a["alias"] for rows in aliases.values() for a in rows]
    assert [n for n in names if any(m in n for m in markup)] == []
