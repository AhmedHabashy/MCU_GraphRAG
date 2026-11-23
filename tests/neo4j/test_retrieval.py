"""Checks on the retrieval layer in the loaded graph (run after src.retrieval.passages).

Run with:  .venv\\Scripts\\python.exe -m pytest -m neo4j
"""

import pytest

from src.retrieval.passages import INDEX, PLOTS_DIR, plot_passages
from src.source_data_collection.storage import read_json
from tests.neo4j.test_graph import count, db  # noqa: F401  (the db fixture)

pytestmark = pytest.mark.neo4j


@pytest.fixture(scope="module")
def passages():
    return [p for path in sorted(PLOTS_DIR.glob("*.json")) for p in plot_passages(read_json(path))]


@pytest.fixture(scope="module")
def loaded(db):  # noqa: F811
    if not count(db, "MATCH (p:Passage) RETURN count(p) AS n"):
        pytest.skip("passages not loaded; run src.retrieval.passages")
    return db


def test_every_passage_is_loaded_once_and_linked_to_its_title(loaded, passages):
    assert count(loaded, "MATCH (p:Passage) RETURN count(p) AS n") == len(passages)
    assert count(loaded, "MATCH (p:Passage) WHERE NOT (p)-[:FROM]->(:Title {qid: p.title_qid}) RETURN count(p) AS n") == 0


def test_every_title_with_a_plot_has_passages(loaded, passages):
    with_plot = {p["title_qid"] for p in passages}
    found = {r["q"] for r in loaded("MATCH (p:Passage) RETURN DISTINCT p.title_qid AS q")}
    assert found == with_plot and len(with_plot) > 90


def test_the_vector_index_is_online_and_finds_a_passage_by_its_own_vector(loaded):
    state = loaded("SHOW VECTOR INDEXES YIELD name, state WHERE name = $name RETURN state", name=INDEX)
    assert state and state[0]["state"] == "ONLINE"
    rows = loaded(f"""MATCH (p:Passage) WITH p LIMIT 1
                      MATCH (q:Passage) SEARCH q IN (VECTOR INDEX {INDEX} FOR p.embedding LIMIT 1)
                      RETURN q.id = p.id AS same""")
    assert rows[0]["same"]


# --- the tools ----------------------------------------------------------------------------

class StoredVector:
    """An embedder that returns the vector of one loaded passage (no network)."""
    embedding_model = "stored"

    def __init__(self, db, heading):
        self.vector = db("MATCH (p:Passage {heading: $h}) RETURN p.embedding AS v LIMIT 1", h=heading)[0]["v"]

    def embed(self, texts):
        return [self.vector for _ in texts]


@pytest.fixture(scope="module")
def tools(loaded):
    from src.graph.neo4j_db import connect
    from src.retrieval.tools import GraphTools
    driver = connect()
    yield GraphTools(driver, StoredVector(loaded, "The Fantastic Four: First Steps"))
    driver.close()


WRITES = ["CREATE (:Title {qid: 'QX'})",
          "MERGE (:Title {qid: 'QX'})",
          "MATCH (t:Title {qid: 'Q23781155'}) SET t.title = 'X'",
          "MATCH (t:Title {qid: 'Q23781155'}) REMOVE t.title",
          "MATCH (t:Title {qid: 'Q23781155'}) DETACH DELETE t",
          "MATCH (t:Title {qid: 'Q23781155'}) CALL (t) { SET t.hacked = true }",
          "CALL db.createLabel('Hacked')",
          "CREATE INDEX hacked IF NOT EXISTS FOR (n:Title) ON (n.hacked)"]


@pytest.mark.parametrize("query", WRITES)
def test_run_cypher_rejects_every_write_and_leaves_the_graph_unchanged(loaded, tools, query):
    before = count(loaded, "MATCH (n) RETURN count(n) AS n")
    assert "error" in tools.run_cypher(query)
    assert count(loaded, "MATCH (n) RETURN count(n) AS n") == before
    assert loaded("MATCH (t:Title {qid: 'Q23781155'}) RETURN t.title AS t, t.hacked AS h")[0].values() == [
        "Avengers: Endgame", None]


def test_run_cypher_returns_rows_caps_them_and_hides_embeddings(tools):
    assert tools.run_cypher("MATCH (t:Title {qid: 'Q23781155'}) RETURN t.title AS title;") == {
        "rows": [{"title": "Avengers: Endgame"}]}
    capped = tools.run_cypher("UNWIND range(1, 500) AS i RETURN i")
    assert len(capped["rows"]) == 200 and "LIMIT" in capped["note"]
    passage = tools.run_cypher("MATCH (p:Passage) RETURN p LIMIT 1")["rows"][0]["p"]
    assert "embedding" not in passage and passage["labels"] == ["Passage"]


def test_run_cypher_reports_errors_for_the_model_to_fix(tools):
    assert "Neo.ClientError.Statement.SyntaxError" in tools.run_cypher("MATCH (t:Title RETURN t")["error"]


def test_find_entity_reaches_a_character_by_an_alias_and_needs_every_word_first(tools):
    """The cover identity is also a Thing (Natasha IMPERSONATES it); Natalie Washington has one word only."""
    found = [(m["label"], m["name"]) for m in tools.find_entity("Natalie Rushman")["matches"]]
    assert ("Character", "Natasha Romanoff") in found and ("Character", "Natalie Washington") not in found


def test_find_entity_falls_back_to_any_word(tools):
    assert any(m["name"] == "Tony Stark" for m in tools.find_entity("Tony Starkk")["matches"])


def test_find_entity_shows_every_variant_of_a_name(tools):
    lokis = [m for m in tools.find_entity("Loki")["matches"] if m["label"] == "Character" and m["name"] == "Loki"]
    assert len({m["id"] for m in lokis}) > 1 and all(m["for_example"] for m in lokis)


def test_search_plots_fuses_the_vector_and_keyword_rankings(tools):
    """The stored vector is a Fantastic Four passage's; the keyword is Vormir's (Infinity War, Endgame)."""
    titles = [p["title"] for p in tools.search_plots("Vormir")["passages"]]
    assert "The Fantastic Four: First Steps" in titles
    assert {"Avengers: Infinity War", "Avengers: Endgame"} <= set(titles)
