"""Unit tests for src/graph/load_neo4j.py (row building only; no database)."""

from src.graph.load_neo4j import (
    birth_dates, crew_rows, fact_rows, follows_rows, mark_cameos, name_index, performance_rows, team_presence, title_rows,
)

TEAMS = [{"id": "X-Men@Earth-92131", "name": "X-Men", "reality": "Earth-92131", "aliases": []},
         {"id": "New Avengers@Earth-616", "name": "New Avengers", "reality": "Earth-616",
          "aliases": ["Thunderbolts", "B-Vengers"]}]
CHARACTERS = [{"id": "N@Earth-616", "label": "Natasha Romanoff", "reality": "Earth-616",
               "aliases": ["Black Widow", "Natalie Rushman"]},
              {"id": "Y@Earth-616", "label": "Yelena Belova", "reality": "Earth-616", "aliases": ["Black Widow"]},
              {"id": "L1@Earth-616", "label": "Loki", "reality": "Earth-616", "aliases": []},
              {"id": "L2@Earth-616", "label": "Loki", "reality": "Earth-616", "aliases": []},
              {"id": "K@Earth-616", "label": "Kang the Conqueror", "reality": "Earth-616", "aliases": ["Victor Timely"]},
              {"id": "V@Earth-616", "label": "Victor Timely", "reality": "Earth-616", "aliases": []}]
# a team's reality and the titles where one of its wiki members appears (team_presence)
PRESENCE = {"X-Men@Earth-92131": ("Earth-92131", {"QX"}), "New Avengers@Earth-616": ("Earth-616", {"Q1", "QD"})}


def fact(subject_id="", subject_name="", obj_id="", obj_name="", obj_type="character", relation="ALLY_OF"):
    return {"subject_id": subject_id, "subject_name": subject_name, "relation": relation, "object_id": obj_id,
            "object_name": obj_name, "object_type": obj_type, "episode": None, "evidence": "e", "note": ""}


def load_facts(*facts, title="Q1", reality="Earth-616"):
    return fact_rows({"c1": {"title_qid": title, "facts": list(facts)}}, {title: reality}, PRESENCE,
                     name_index(TEAMS, "name"), name_index(CHARACTERS, "label"))


def ends(edges, relation):
    return [(e["from_label"], e["from"], e["to_label"], e["to"]) for e in edges[relation]]


def test_linked_ends_are_characters_or_teams_by_id():
    _, edges = load_facts(fact("C@Earth-616", "Yelena", "New Avengers@Earth-616", "New Avengers", "team", "MEMBER_OF"))
    assert ends(edges, "MEMBER_OF") == [("Character", "C@Earth-616", "Team", "New Avengers@Earth-616")]


def test_a_team_of_another_reality_is_linked_only_when_one_of_its_members_appears_in_the_title():
    """What If...? (Multiverse) facts were linked to the Earth-616 S.H.I.E.L.D.; Doomsday (Earth-616)
    rightly links the Earth-828 Fantastic Four, whose members appear in it."""
    _, edges = load_facts(fact("C@Earth-616", "Yelena", "New Avengers@Earth-616", "New Avengers", "team", "MEMBER_OF"),
                          title="QD", reality="Earth-828")
    assert edges["MEMBER_OF"][0]["to"] == "New Avengers@Earth-616"           # a member appears in QD
    things, edges = load_facts(fact("C@Multiverse", "Hope", "New Avengers@Earth-616", "New Avengers", "team",
                                    "MEMBER_OF"), title="QW", reality="Multiverse")
    assert ends(edges, "MEMBER_OF") == [("Character", "C@Multiverse", "Thing", "team:new avengers@Multiverse")]
    _, edges = load_facts(fact("C@Earth-92131", "Logan", "New Avengers@Earth-616", "X-Men", "team", "MEMBER_OF"),
                          title="QX2", reality="Earth-92131")
    assert edges["MEMBER_OF"][0]["to"] == "X-Men@Earth-92131"    # resolved by name in the title's own reality


def test_an_unlinked_group_is_the_team_of_that_name_or_alias_in_the_titles_reality():
    _, edges = load_facts(fact("C@Earth-616", "Yelena", "", "the Thunderbolts", "team", "MEMBER_OF"))
    assert edges["MEMBER_OF"][0]["to_label"] == "Team" and edges["MEMBER_OF"][0]["to"] == "New Avengers@Earth-616"
    _, edges = load_facts(fact("C@Earth-10005", "Logan", "", "X-Men", "team", "MEMBER_OF"), reality="Earth-10005")
    assert edges["MEMBER_OF"][0]["to_label"] == "Thing"     # no X-Men team row for that reality


def test_an_unlinked_character_is_the_one_character_of_that_name_else_of_that_alias():
    _, edges = load_facts(fact("", "Natalie Rushman", "", "Victor Timely", "character", "IMPERSONATES"))
    # Natalie Rushman is only an alias; Victor Timely is one character's name and another's alias
    assert ends(edges, "IMPERSONATES") == [("Character", "N@Earth-616", "Character", "V@Earth-616")]


def test_a_name_of_the_other_end_itself_stays_a_thing():
    """A cover identity, a symbiote or a transformed form is named apart from the character in
    the plot; linking it would make a self-loop. Self-facts given by ID (suicides) are kept."""
    things, edges = load_facts(fact("N@Earth-616", "Natasha", "", "Natalie Rushman", "character", "IMPERSONATES"),
                               fact("N@Earth-616", "Natasha", "N@Earth-616", "Natasha", "character", "KILLS"))
    assert ends(edges, "IMPERSONATES") == [("Character", "N@Earth-616", "Thing", "character:natalie rushman@Earth-616")]
    assert ends(edges, "KILLS") == [("Character", "N@Earth-616", "Character", "N@Earth-616")]


def test_an_unlinked_character_stays_a_thing_when_its_name_is_shared_or_from_another_reality():
    things, _ = load_facts(fact("", "Natasha Romanoff", "", "Hydra", "organization", "ENEMY_OF"), reality="Multiverse")
    assert {t["key"] for t in things} == {"character:natasha romanoff@Multiverse", "organization:hydra@Multiverse"}
    things, _ = load_facts(fact("", "Loki", "", "Black Widow", "character", "ENEMY_OF"))
    assert {t["key"] for t in things} == {"character:loki@Earth-616", "character:black widow@Earth-616"}


def test_other_unlinked_ends_are_things_shared_within_a_reality():
    things, edges = load_facts(fact("C@Earth-616", "Loki", "", "Tesseract", "object", "POSSESSES"),
                               fact("D@Earth-616", "Thor", "", "tesseract", "object", "POSSESSES"),
                               fact("", "Time-Keepers", "C@Earth-616", "Loki", "character", "ENEMY_OF"))
    assert {t["key"] for t in things} == {"object:tesseract@Earth-616", "character:time keepers@Earth-616"}
    assert edges["ENEMY_OF"][0]["from_label"] == "Thing"


def test_a_thing_typed_once_as_a_group_takes_that_type_over_the_default_character_type():
    things, edges = load_facts(fact("", "Ravagers", "C@Earth-616", "Yondu", "character", "WORKS_FOR"),
                               fact("C@Earth-616", "Yondu", "", "the Ravagers", "organization", "LEADS"))
    assert [(t["key"], t["type"]) for t in things] == [("organization:ravagers@Earth-616", "organization")]
    assert edges["WORKS_FOR"][0]["from"] == edges["LEADS"][0]["to"]


def test_a_name_given_two_other_types_keeps_one_thing_per_type():
    things, _ = load_facts(fact("C@Earth-616", "Shang-Chi", "", "Ten Rings", "object", "POSSESSES"),
                           fact("C@Earth-616", "Shang-Chi", "", "Ten Rings", "organization", "ENEMY_OF"),
                           fact("", "Ten Rings", "C@Earth-616", "Shang-Chi", "character", "ENEMY_OF"))
    assert {t["type"] for t in things} == {"object", "organization", "character"}


def test_an_unlinked_place_is_not_matched_to_a_team_or_character():
    things, _ = load_facts(fact("C@Earth-616", "Yelena", "", "Thunderbolts", "place", "TRAVELS_TO"),
                           fact("C@Earth-616", "Yelena", "", "Loki", "place", "TRAVELS_TO"))
    assert sorted(t["type"] for t in things) == ["place", "place"]


def test_team_presence_is_the_titles_where_a_wiki_member_appears():
    teams = [{"id": "A@E", "reality": "E"}, {"id": "B@E", "reality": "E"}]
    memberships = [{"team_id": "A@E", "character_id": "c1"}, {"team_id": "A@E", "character_id": "c2"}]
    appears = [{"character": "c1", "title": "T1"}, {"character": "c2", "title": "T2"}, {"character": "c3", "title": "T3"}]
    assert team_presence(teams, memberships, appears) == {"A@E": ("E", {"T1", "T2"}), "B@E": ("E", set())}


def perf(cid, actor_qid, tmdb_id, name, credit, billing=""):
    return {"character_id": cid, "title_qid": "Q1", "actor_qid": actor_qid, "tmdb_person_id": tmdb_id,
            "actor_name": name, "tmdb_character": credit, "billing_order": billing}


def test_performances_give_one_person_and_one_plays_edge_per_title_with_the_best_billing():
    perfs = [perf("C@E", "QA", "1", "A", "Logan", "3"), perf("C@E", "QA", "1", "A", "", "1"),
             perf("C@E", "", "2", "B", "Logan (young)"), perf("", "QX", "", "Stan Lee", "Bus Driver")]
    people, plays, appears, acted = performance_rows(perfs)
    assert sorted(people) == ["QA", "QX", "tmdb:2"]
    assert [(p["person"], p["credited_as"], p["billing_order"]) for p in plays] == [
        ("QA", ["Logan"], 1), ("tmdb:2", ["Logan (young)"], None)]
    assert appears == [{"character": "C@E", "title": "Q1"}]
    # every credit with a person counts as acting in the title, linked or not (Stan Lee's cameos)
    assert acted == [{"person": "QA", "title": "Q1", "cameo": False}, {"person": "QX", "title": "Q1", "cameo": False},
                     {"person": "tmdb:2", "title": "Q1", "cameo": False}]


def test_a_cameo_persons_credits_are_cameos_and_a_character_with_only_cameo_credits_is_one():
    perfs = [perf("W@E", "Q181900", "", "Stan Lee", "Thirsty Gambler"), perf("F@E", "QA", "1", "A", "Nick Fury"),
             perf("F@E", "Q181900", "", "Stan Lee", "Fury (voice)")]
    _, plays, _, acted = performance_rows(perfs)
    assert [(p["character"], p["cameo"]) for p in plays] == [("W@E", True), ("F@E", False), ("F@E", True)]
    assert {(a["person"], a["cameo"]) for a in acted} == {("Q181900", True), ("QA", False)}
    characters = [{"id": "W@E"}, {"id": "F@E"}, {"id": "N@E"}]
    mark_cameos(characters, plays)
    assert [c["cameo"] for c in characters] == [True, False, False]      # no credits at all: not a cameo


REGISTRY = [{"wikidata_qid": "Q1", "title": "Iron Man", "type": "Film", "year": "2008", "universe": "MCU",
             "reality": "Earth-616", "tier": "1"}]


def test_title_rows_merge_release_phases_and_timeline():
    rows = title_rows(REGISTRY, {"Q1": {"first_release_date": "2008-04-14", "release_order": "15"}},
                      {"Q1": {"phases": "Phase One", "sagas": "The Infinity Saga"}}, {}, {}, {})
    assert rows[0]["release_order"] == 15 and rows[0]["phases"] == ["Phase One"]
    assert rows[0]["chronological_order"] is None and rows[0]["start_year"] is None


def test_money_is_wikidatas_else_tmdbs_and_says_which():
    money = {"Q1": {"box_office_usd": "", "cost_usd": "140000000", "duration_minutes": "126"}}
    stats = {"Q1": {"revenue_usd": "585174222", "budget_usd": "1", "runtime_minutes": "1", "vote_average": "7.668",
                    "vote_count": "29220"}}
    r = title_rows(REGISTRY, {}, {}, {}, money, stats)[0]
    assert (r["box_office_usd"], r["box_office_source"]) == (585174222, "tmdb")
    assert (r["budget_usd"], r["budget_source"], r["runtime_minutes"]) == (140000000, "wikidata", 126)
    assert (r["tmdb_rating"], r["tmdb_votes"]) == (7.668, 29220)


def test_years_are_the_mcu_wikis_else_wikipedias():
    both = {"Q1": {"mcu_wiki_start_year": "2018", "mcu_wiki_end_year": "2023",
                   "wikipedia_start_year": "2023", "wikipedia_end_year": "2023"}}
    only_wp = {"Q1": {"mcu_wiki_start_year": "", "mcu_wiki_end_year": "",
                      "wikipedia_start_year": "-1260", "wikipedia_end_year": "-1260"}}
    r1, r2 = title_rows(REGISTRY, {}, {}, both, {}, {})[0], title_rows(REGISTRY, {}, {}, only_wp, {}, {})[0]
    assert (r1["start_year"], r1["end_year"], r1["years_source"]) == (2018, 2023, "mcu_wiki")
    assert (r2["start_year"], r2["years_source"]) == (-1260, "wikipedia")


def test_directors_and_writers_join_the_people_once():
    people = {"Q295964": {"key": "Q295964", "qid": "Q295964", "tmdb_id": "15277", "name": "Jon Favreau"}}
    details = [{"title_qid": "Q1", "director_qids": "Q295964", "director_names": "Jon Favreau",
                "writer_qids": "Q615343|Q3128755", "writer_names": "Mark Fergus|Hawk Ostby"}]
    edges = crew_rows(details, people)
    assert edges["DIRECTED"] == [{"person": "Q295964", "title": "Q1"}] and len(edges["WROTE"]) == 2
    assert sorted(people) == ["Q295964", "Q3128755", "Q615343"]   # Favreau (actor) is not duplicated


def test_birth_date_is_wikidatas_single_date_else_tmdbs():
    people = {"QA": {"qid": "QA", "tmdb_id": "1"}, "QB": {"qid": "QB", "tmdb_id": "2"}, "tmdb:3": {"qid": "", "tmdb_id": "3"}}
    birth_dates(people, [{"actor_qid": "QA", "birth_dates": "1965-04-04"}, {"actor_qid": "QB", "birth_dates": "1970-01-01|1971-01-01"}],
                [{"tmdb_person_id": "2", "birthday": "1970-01-01"}, {"tmdb_person_id": "3", "birthday": "1980-05-05"}])
    assert [people[k]["birth_date"] for k in ("QA", "QB", "tmdb:3")] == ["1965-04-04", "1970-01-01", "1980-05-05"]


def test_follows_keeps_only_titles_in_scope():
    details = [{"title_qid": "Q2", "follows_qids": "Q1|Q99"}, {"title_qid": "Q1", "follows_qids": ""}]
    assert follows_rows(details) == [{"title": "Q2", "previous": "Q1"}]
