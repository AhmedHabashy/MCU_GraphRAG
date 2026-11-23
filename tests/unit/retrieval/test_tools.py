"""Unit tests for src/retrieval/tools.py (no database: pure helpers and dispatch)."""

import json

from neo4j.graph import Graph, Node

from src.retrieval.tools import GraphTools, SCHEMAS, fuse, lucene_text, plain, truncate_rows


def test_lucene_text_drops_query_syntax():
    assert lucene_text('Loki: "God" of (Mischief)?*') == "Loki God of Mischief"
    assert lucene_text("AND OR NOT") == "and or not"          # operators become plain words


def test_fuse_ranks_by_reciprocal_rank_over_both_lists():
    assert fuse([["a", "b", "c"], ["c", "a"]]) == ["a", "c", "b"]
    assert fuse([[], ["x"]]) == ["x"]


def test_plain_turns_nodes_and_relationships_into_dicts_without_embeddings():
    node = Node(Graph(), "4:x:1", 1, ["Passage"], {"id": "p1", "text": "t", "embedding": [0.1] * 3})
    assert plain(node) == {"labels": ["Passage"], "id": "p1", "text": "t"}
    assert plain({"n": [node, 3]}) == {"n": [{"labels": ["Passage"], "id": "p1", "text": "t"}, 3]}


def test_rows_are_cut_to_the_character_budget_and_say_so():
    rows = [{"x": "a" * 100} for _ in range(50)]
    kept, truncated = truncate_rows(rows, max_chars=1000)
    assert truncated and 0 < len(kept) < 50 and len(json.dumps(kept)) <= 1000
    assert truncate_rows(rows[:2], max_chars=1000) == (rows[:2], False)


class FakeTools(GraphTools):
    def __init__(self):
        pass

    def find_entity(self, name, limit=10):
        return {"matches": [name, limit]}


def test_call_dispatches_by_name_and_returns_json_errors_instead_of_raising():
    tools = FakeTools()
    assert json.loads(tools.call("find_entity", '{"name": "Loki"}')) == {"matches": ["Loki", 10]}
    assert "error" in json.loads(tools.call("find_entity", "{not json"))
    assert "error" in json.loads(tools.call("drop_database", "{}"))
    assert "error" in json.loads(tools.call("find_entity", '{"wrong": 1}'))


def test_every_schema_names_a_tool_method_and_its_required_arguments():
    for schema in SCHEMAS:
        fn = schema["function"]
        assert callable(getattr(GraphTools, fn["name"]))
        assert set(fn["parameters"]["required"]) <= set(fn["parameters"]["properties"])
