"""Checks on the loaded graph (run after src.graph.load_neo4j).

Run with:  .venv\\Scripts\\python.exe -m pytest -m neo4j
"""

import pytest
from neo4j.exceptions import ServiceUnavailable

from src.graph.check_extraction import RELATIONS
from src.graph.load_neo4j import KEYS, read_data
from src.graph.neo4j_db import connect

pytestmark = pytest.mark.neo4j


@pytest.fixture(scope="module")
def db():
    driver = connect()
    try:
        driver.verify_connectivity()
    except ServiceUnavailable:
        driver.close()
        pytest.skip("Neo4j is not running; start it with `docker compose up -d`")
    if not driver.execute_query("MATCH (n:Title) RETURN count(n) AS n").records[0]["n"]:
        driver.close()
        pytest.skip("graph not loaded; run src.graph.load_neo4j")
    yield lambda query, **params: driver.execute_query(query, **params).records
    driver.close()


@pytest.fixture(scope="module")
def data():
    return read_data()


def count(db, query):
    return db(query)[0]["n"]


@pytest.mark.parametrize("label, table", [("Title", "titles"), ("Character", "characters"), ("Actor", "actors"),
                                          ("Team", "teams"), ("Thing", "things")])
def test_every_table_row_is_one_node(db, data, label, table):
    assert count(db, f"MATCH (n:{label}) RETURN count(n) AS n") == len(data[table])


def test_every_plot_fact_is_loaded(db, data):
    expected = sum(len(rows) for rows in data["facts"].values())
    assert count(db, "MATCH ()-[r]->() WHERE r.source = 'plot' RETURN count(r) AS n") == expected


def test_every_wiki_membership_variant_and_performance_is_loaded(db, data):
    assert count(db, "MATCH ()-[r:MEMBER_OF]->() WHERE r.source <> 'plot' RETURN count(r) AS n") == len(data["memberships"])
    assert count(db, "MATCH ()-[r:VARIANT_OF]->() WHERE r.source IS NULL RETURN count(r) AS n") == len(data["variants"])
    assert count(db, "MATCH ()-[r:PLAYS]->() RETURN count(r) AS n") == len(data["plays"])


def test_every_character_appears_in_a_title(db):
    assert count(db, "MATCH (c:Character) WHERE NOT (c)-[:APPEARS_IN]->() RETURN count(c) AS n") == 0


def test_node_keys_are_unique_constraints(db):
    found = {(r["label"], r["prop"]) for r in db(
        "SHOW CONSTRAINTS YIELD labelsOrTypes, properties, type WHERE type = 'NODE_PROPERTY_UNIQUENESS' "
        "RETURN labelsOrTypes[0] AS label, properties[0] AS prop")}
    assert set(KEYS.items()) <= found


def test_only_known_relation_types(db):
    types = {r["t"] for r in db("MATCH ()-[r]->() RETURN DISTINCT type(r) AS t")}
    assert types <= set(RELATIONS) | {"APPEARS_IN", "PLAYS", "VARIANT_OF", "MEMBER_OF"}


def test_daisy_johnson_is_an_inhuman_in_shield(db):
    rows = db("MATCH (c:Character {id: 'Q24027972@Earth-616'})-[m:MEMBER_OF]->(t:Team {id: 'S.H.I.E.L.D.@Earth-616'}) "
              "WHERE m.source <> 'plot' RETURN c.species AS species LIMIT 1")
    assert rows and rows[0]["species"] == ["Inhuman"]


def test_mobius_is_a_tva_agent_played_by_owen_wilson(db):
    rows = db("MATCH (a:Actor)-[:PLAYS]->(c:Character)-[:MEMBER_OF]->(:Team {id: 'Time Variance Authority@Earth-616'}) "
              "WHERE c.label STARTS WITH 'Mobius' RETURN a.name AS actor LIMIT 1")
    assert rows and rows[0]["actor"] == "Owen Wilson"


def test_unlinked_group_names_reach_their_team(db, data):
    """Some facts name a team only in text (no ID); the loader links them by name or alias."""
    by_name = [r for rows in data["facts"].values() for r in rows if r["to_label"] == "Team"]
    assert by_name and count(db, "MATCH ()-[r {source: 'plot'}]->(:Team) RETURN count(r) AS n") == len(by_name)


def test_a_plot_fact_keeps_its_evidence(db):
    """Loki season 1: Sylvie kills He Who Remains (pilot fact, checked by hand)."""
    rows = db("MATCH (:Character {label: 'Sylvie'})-[r:KILLS {title_qid: 'Q107185252'}]->(v:Character) "
              "RETURN v.label AS victim, r.evidence AS evidence")
    assert any(r["victim"] == "He Who Remains" and r["evidence"] for r in rows)
