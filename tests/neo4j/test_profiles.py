"""Checks on the character profiles in the loaded graph (run after src.graph.profiles).

Run with:  .venv\\Scripts\\python.exe -m pytest -m neo4j
"""

import pytest

from tests.neo4j.test_graph import count, db  # noqa: F401  (the db fixture)

pytestmark = pytest.mark.neo4j


@pytest.fixture(scope="module")
def profiles(db):  # noqa: F811
    if not count(db, "MATCH (c:Character) WHERE c.profile IS NOT NULL RETURN count(c) AS n"):
        pytest.skip("profiles not written; run src.graph.profiles")
    return lambda cid: db("MATCH (c:Character {id: $id}) RETURN c.profile AS p", id=cid)[0]["p"]


def test_every_character_has_a_profile(db, profiles):  # noqa: F811
    assert count(db, "MATCH (c:Character) WHERE c.profile IS NULL OR c.profile = '' RETURN count(c) AS n") == 0


def test_wanda_names_her_actor_and_both_variants(profiles):
    wanda = profiles("Q24022542@Earth-616")
    assert wanda.startswith("Wanda Maximoff (Earth-616).")
    assert "Elizabeth Olsen" in wanda
    assert "(Multiverse: What If...?" in wanda and "(Earth-89521: Marvel Zombies" in wanda


def test_natashas_names_include_her_cover_identity(profiles):
    assert "Natalie Rushman" in profiles("Q23895063@Earth-616").splitlines()[0]


def test_each_of_hugh_jackmans_characters_names_him_and_its_own_reality(db, profiles):  # noqa: F811
    rows = db("MATCH (:Person {name: 'Hugh Jackman'})-[:PLAYS]->(c:Character) RETURN DISTINCT c.id AS id, "
              "c.label AS label, c.reality AS reality")
    assert len({r["reality"] for r in rows}) >= 3
    for r in rows:
        assert profiles(r["id"]).startswith(f"{r['label']} ({r['reality']}).") and "Hugh Jackman" in profiles(r["id"])


def test_appearances_are_in_release_order(profiles):
    line = next(l for l in profiles("Q24022542@Earth-616").splitlines() if l.startswith("Appears in"))
    assert line.index("Captain America: The Winter Soldier") < line.index("Avengers: Age of Ultron") \
        < line.index("Avengers: Endgame")
