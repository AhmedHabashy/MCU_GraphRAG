"""Checks on the search indexes built by src.retrieval.indexes (docs/rag_design.md, "Index set").

Run with:  .venv\\Scripts\\python.exe -m pytest -m neo4j
"""

import statistics
import time

import pytest

from src.graph.load_neo4j import KEYS, NAME_INDEX
from src.retrieval.indexes import FULLTEXT, LOOKUP, VECTOR
from tests.neo4j.test_graph import count, db  # noqa: F401  (the db fixture)

pytestmark = pytest.mark.neo4j
DIMENSIONS = 1536            # text-embedding-3-small
MAX_SECONDS = 0.05


@pytest.fixture(scope="module")
def indexed(db):  # noqa: F811
    if not count(db, "MATCH (p:Passage) RETURN count(p) AS n"):
        pytest.skip("search indexes not built; run src.retrieval.indexes")
    return db


def timed(db, query, **params):  # noqa: F811
    """(rows, median seconds of three runs); a first run plans the query and warms the index."""
    rows, seconds = db(query, **params), []
    for _ in range(3):
        start = time.perf_counter()
        db(query, **params)
        seconds.append(time.perf_counter() - start)
    return rows, statistics.median(seconds)


def test_every_index_exists_is_online_and_nothing_stale_is_left(indexed):
    rows = indexed("SHOW INDEXES YIELD name, type, state WHERE type <> 'LOOKUP' RETURN name, state")
    keys = {f"{label.lower()}_{key}" for label, key in KEYS.items()} | {"summary_id", "passage_id"}
    assert {r["name"] for r in rows} == keys | {NAME_INDEX} | set(FULLTEXT) | set(VECTOR) | set(LOOKUP)
    assert {r["state"] for r in rows} == {"ONLINE"}


def test_every_passage_fact_and_summary_has_a_vector_of_the_models_size(indexed):
    for query in ("MATCH (n:Passage) RETURN n.embedding AS v",
                  "MATCH ()-[n]->() WHERE n.source = 'plot' RETURN n.embedding AS v",
                  "MATCH (n:Summary) RETURN n.embedding AS v"):
        assert {len(r["v"]) if r["v"] else 0 for r in indexed(query)} == {DIMENSIONS}, query
    assert count(indexed, "MATCH (p:Passage) WHERE NOT (p)-[:FROM]->(:Title) RETURN count(p) AS n") == 0


def test_an_alias_finds_its_character(indexed):
    """The Thing "Natalie Rushman" (Natasha IMPERSONATES it in Iron Man 2) ranks above her."""
    rows, seconds = timed(indexed, f"""CALL db.index.fulltext.queryNodes('{NAME_INDEX}', '"Natalie Rushman"')
                                       YIELD node WHERE node:Character RETURN node.label AS label LIMIT 1""")
    assert rows[0]["label"] == "Natasha Romanoff" and seconds < MAX_SECONDS


def test_a_place_finds_its_plot_passages(indexed):
    rows, seconds = timed(indexed, """CALL db.index.fulltext.queryNodes('passage_text', 'Vormir') YIELD node
                                     MATCH (node)-[:FROM]->(t:Title) RETURN DISTINCT t.title AS title""")
    assert {"Avengers: Infinity War", "Avengers: Endgame"} <= {r["title"] for r in rows} and seconds < MAX_SECONDS


def test_words_find_plot_facts_by_their_evidence(indexed):
    rows, seconds = timed(indexed, """CALL db.index.fulltext.queryRelationships('evidence_text', '"Soul Stone"')
                                     YIELD relationship MATCH (t:Title {qid: relationship.title_qid})
                                     RETURN DISTINCT t.title AS title""")
    assert "Avengers: Infinity War" in {r["title"] for r in rows} and seconds < MAX_SECONDS     # no Endgame fact names it


def test_words_find_summaries(indexed):
    rows, seconds = timed(indexed, """CALL db.index.fulltext.queryNodes('summary_text', '"Soul Stone"') YIELD node
                                     MATCH (node {kind: 'title'})-[:SUMMARIZES]->(t:Title) RETURN t.title AS title""")
    assert {"Avengers: Infinity War", "Avengers: Endgame"} <= {r["title"] for r in rows} and seconds < MAX_SECONDS


@pytest.mark.parametrize("index, query, key", [
    ("passage_embedding", "MATCH (n:Passage) RETURN n.id AS key, n.embedding AS v LIMIT 1", "n.id"),
    ("summary_embedding", "MATCH (n:Summary) RETURN n.id AS key, n.embedding AS v LIMIT 1", "n.id"),
])
def test_a_node_vector_finds_itself_first(indexed, index, query, key):
    row = indexed(query)[0]
    rows, seconds = timed(indexed, f"""CALL db.index.vector.queryNodes('{index}', 1, $v) YIELD node AS n
                                       RETURN {key} AS key""", v=row["v"])
    assert rows[0]["key"] == row["key"] and seconds < MAX_SECONDS


def test_a_fact_vector_finds_itself_first(indexed):
    row = indexed("MATCH ()-[r:KILLS]->() WHERE r.source = 'plot' RETURN elementId(r) AS key, r.embedding AS v LIMIT 1")[0]
    rows, seconds = timed(indexed, """CALL db.index.vector.queryRelationships('evidence_embedding', 1, $v)
                                     YIELD relationship RETURN elementId(relationship) AS key""", v=row["v"])
    assert rows[0]["key"] == row["key"] and seconds < MAX_SECONDS
