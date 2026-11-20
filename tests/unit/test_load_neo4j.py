"""Unit tests for src/graph/load_neo4j.py (row building only; no database)."""

from src.graph.load_neo4j import fact_rows, performance_rows, team_index, title_rows

TEAMS = [{"team_id": "X-Men@Earth-92131", "name": "X-Men", "reality": "Earth-92131", "aliases": ""},
         {"team_id": "New Avengers@Earth-616", "name": "New Avengers", "reality": "Earth-616",
          "aliases": "Thunderbolts|B-Vengers"}]
TEAM_IDS = {t["team_id"] for t in TEAMS}


def fact(subject_id="", subject_name="", obj_id="", obj_name="", obj_type="character", relation="ALLY_OF"):
    return {"subject_id": subject_id, "subject_name": subject_name, "relation": relation, "object_id": obj_id,
            "object_name": obj_name, "object_type": obj_type, "episode": None, "evidence": "e", "note": ""}


def load_facts(*facts, title="Q1", reality="Earth-616"):
    return fact_rows({"c1": {"title_qid": title, "facts": list(facts)}}, {title: reality}, TEAM_IDS, team_index(TEAMS))


def test_linked_ends_are_characters_or_teams_by_id():
    _, edges = load_facts(fact("C@Earth-616", "Yelena", "New Avengers@Earth-616", "New Avengers", "team", "MEMBER_OF"))
    e = edges["MEMBER_OF"][0]
    assert (e["from_label"], e["from"], e["to_label"], e["to"]) == ("Character", "C@Earth-616", "Team", "New Avengers@Earth-616")


def test_an_unlinked_group_is_the_team_of_that_name_or_alias_in_the_titles_reality():
    _, edges = load_facts(fact("C@Earth-616", "Yelena", "", "the Thunderbolts", "team", "MEMBER_OF"))
    assert edges["MEMBER_OF"][0]["to_label"] == "Team" and edges["MEMBER_OF"][0]["to"] == "New Avengers@Earth-616"
    _, edges = load_facts(fact("C@Earth-10005", "Logan", "", "X-Men", "team", "MEMBER_OF"), reality="Earth-10005")
    assert edges["MEMBER_OF"][0]["to_label"] == "Thing"     # no X-Men team row for that reality


def test_other_unlinked_ends_are_things_shared_within_a_reality():
    things, edges = load_facts(fact("C@Earth-616", "Loki", "", "Tesseract", "object", "POSSESSES"),
                               fact("D@Earth-616", "Thor", "", "tesseract", "object", "POSSESSES"),
                               fact("", "Time-Keepers", "C@Earth-616", "Loki", "character", "ENEMY_OF"))
    assert {t["key"] for t in things} == {"object:tesseract@Earth-616", "character:time keepers@Earth-616"}
    assert edges["ENEMY_OF"][0]["from_label"] == "Thing"


def test_an_unlinked_place_is_not_matched_to_a_team():
    things, _ = load_facts(fact("C@Earth-616", "Yelena", "", "Thunderbolts", "place", "TRAVELS_TO"))
    assert [t["type"] for t in things] == ["place"]


def test_performances_give_one_actor_node_and_one_plays_edge_per_title():
    perfs = [{"character_id": "C@E", "title_qid": "Q1", "actor_qid": "QA", "tmdb_person_id": "1", "actor_name": "A",
              "tmdb_character": "Logan"},
             {"character_id": "C@E", "title_qid": "Q1", "actor_qid": "QA", "tmdb_person_id": "1", "actor_name": "A",
              "tmdb_character": ""},
             {"character_id": "C@E", "title_qid": "Q1", "actor_qid": "", "tmdb_person_id": "2", "actor_name": "B",
              "tmdb_character": "Logan (young)"},
             {"character_id": "", "title_qid": "Q1", "actor_qid": "QX", "tmdb_person_id": "", "actor_name": "X",
              "tmdb_character": "Extra"}]
    actors, plays, appears = performance_rows(perfs)
    assert [a["key"] for a in actors] == ["QA", "tmdb:2"]
    assert [(p["actor"], p["credited_as"]) for p in plays] == [("QA", ["Logan"]), ("tmdb:2", ["Logan (young)"])]
    assert appears == [{"character": "C@E", "title": "Q1"}]


def test_title_rows_merge_release_phases_and_timeline():
    registry = [{"wikidata_qid": "Q1", "title": "Iron Man", "type": "Film", "year": "2008", "universe": "MCU",
                 "reality": "Earth-616", "tier": "1"}]
    rows = title_rows(registry, {"Q1": {"first_release_date": "2008-04-14", "release_order": "15"}},
                      {"Q1": {"phases": "Phase One", "sagas": "The Infinity Saga"}}, {})
    assert rows[0]["release_order"] == 15 and rows[0]["phases"] == ["Phase One"]
    assert rows[0]["chronological_order"] is None
