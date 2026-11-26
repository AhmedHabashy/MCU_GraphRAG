"""Checks on the Summary nodes loaded by src.graph.load_summaries.

Run with:  .venv\\Scripts\\python.exe -m pytest -m neo4j
"""

import pytest

from src.graph.summary_inputs import INPUTS_DIR, citations, read_plots
from tests.neo4j.test_graph import count, db  # noqa: F401  (the db fixture)

pytestmark = pytest.mark.neo4j


@pytest.fixture(scope="module")
def loaded(db):  # noqa: F811
    if not count(db, "MATCH (s:Summary) RETURN count(s) AS n"):
        pytest.skip("summaries not loaded; run src.graph.load_summaries")
    return db


def test_every_summary_input_is_one_node_of_its_kind(loaded):
    expected = {}
    for path in INPUTS_DIR.glob("*/*.json"):
        expected[path.parent.name] = expected.get(path.parent.name, 0) + 1
    assert {r["kind"]: r["n"] for r in loaded("MATCH (s:Summary) RETURN s.kind AS kind, count(s) AS n")} == expected


def test_every_summary_links_to_what_it_describes(loaded):
    assert count(loaded, "MATCH (s:Summary) WHERE NOT (s)-[:SUMMARIZES]->() RETURN count(s) AS n") == 0
    # titles, characters and teams: one link, to their own node
    assert count(loaded, """MATCH (s:Summary) WHERE s.kind IN ['title', 'character', 'team']
                            AND COUNT { (s)-[:SUMMARIZES]->() } <> 1 RETURN count(s) AS n""") == 0
    assert count(loaded, """MATCH (s:Summary)-[:SUMMARIZES]->(n) WHERE s.kind IN ['title', 'character', 'team']
                            AND s.id <> s.kind + ':' + coalesce(n.qid, n.id) RETURN count(s) AS n""") == 0
    assert count(loaded, "MATCH (t:Title) WHERE NOT (:Summary {kind: 'title'})-[:SUMMARIZES]->(t) RETURN count(t) AS n") == 0


def test_a_group_links_to_its_titles(loaded):
    phase_one = [r["name"] for r in loaded("""MATCH (:Summary {id: 'phase:Phase One'})-[:SUMMARIZES]->(t:Title)
                                           RETURN t.title AS name ORDER BY t.release_order""")]
    assert phase_one == ["Iron Man", "The Incredible Hulk", "Iron Man 2", "Thor", "Captain America: The First Avenger",
                         "The Avengers"]
    assert count(loaded, """MATCH (t:Title) WHERE 'The Infinity Saga' IN t.sagas
                            AND NOT (:Summary {id: 'saga:The Infinity Saga'})-[:SUMMARIZES]->(t)
                            RETURN count(t) AS n""") == 0
    assert count(loaded, """MATCH (s:Summary {kind: 'season'})-[l:SUMMARIZES]->(t:Title)
                            WHERE s.id <> 'season:' + t.qid + '-s' + toString(l.season) RETURN count(s) AS n""") == 0


def test_every_title_summary_reaches_its_universe_summary(loaded):
    assert count(loaded, """MATCH (ts:Summary {kind: 'title'})-[:SUMMARIZES]->(t:Title),
                                  (us:Summary {kind: 'universe', id: 'universe:' + t.universe})
                            WHERE NOT (ts)-[:PART_OF*]->(us) RETURN count(ts) AS n""") == 0
    assert [r["id"] for r in loaded("""MATCH (:Summary {id: 'phase:Phase Three'})-[:PART_OF]->(s:Summary)
                                       RETURN s.id AS id ORDER BY id""")] == ["saga:The Infinity Saga", "universe:MCU"]


def test_every_key_fact_cites_a_real_title_and_episode(loaded):
    plots = read_plots()
    episodes = {q: {e["number_overall"] for e in p.get("episodes") or []} for q, p in plots.items()}
    bad = []
    for r in loaded("MATCH (s:Summary) RETURN s.id AS id, s.key_facts AS facts, s.key_fact_cites AS cites"):
        assert len(r["facts"]) == len(r["cites"]) > 0, r["id"]
        bad += [(r["id"], q, ep) for c in r["cites"] for q, ep in citations(c)
                if q not in plots or (ep is not None and ep not in episodes[q])]
    assert bad == []
