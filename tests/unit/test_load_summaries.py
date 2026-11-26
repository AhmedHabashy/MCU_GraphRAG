"""Unit tests for src/graph/load_summaries.py (no database, no files)."""

import pytest

from src.graph.load_summaries import kept, summary_rows


def item(kind, id_, level, sources, facts=()):
    inp = {"kind": kind, "id": id_, "level": level, "sources": sources, "input_hash": f"h-{id_}"}
    out = {"name": f"N {id_}", "summary": f"S {id_}", "input_hash": f"h-{id_}", "writer": "w",
           "key_facts": [{"fact": f, "cite": c} for f, c in facts]}
    return inp, out


ITEMS = [
    item("title", "Q1", 1, ["Q1"], [("Tony builds a suit.", "[Q1]")]),
    item("title", "Q3", 1, ["Q3"]),
    item("season", "Q5-s1", 1, ["Q5"]),
    item("season", "Q5-s2", 1, ["Q5"]),
    item("title", "Q5", 1, [["season", "Q5-s1"], ["season", "Q5-s2"]]),
    item("character", "Q9@Earth-616", 1, ["Q1", "Q3"]),
    item("team", "Avengers@Earth-616", 1, ["Q3"]),
    item("series", "Q1", 2, [["title", "Q1"], ["title", "Q3"]]),
    item("phase", "Phase One", 2, [["title", "Q1"], ["title", "Q5"]]),
    item("phase", "Phase Two", 2, [["title", "Q3"]]),
    item("saga", "The Infinity Saga", 3, [["phase", "Phase One"], ["phase", "Phase Two"]]),
]


@pytest.fixture(scope="module")
def rows():
    return summary_rows(ITEMS)


def test_a_node_carries_the_text_and_the_key_facts_in_matching_lists(rows):
    node = next(n for n in rows[0] if n["id"] == "title:Q1")
    assert (node["kind"], node["level"], node["text"], node["key_facts"], node["key_fact_cites"]) == \
        ("title", 1, "S Q1", ["Tony builds a suit."], ["[Q1]"])


def test_a_series_and_a_title_with_the_same_qid_are_two_summaries(rows):
    assert {"title:Q1", "series:Q1"} <= {n["id"] for n in rows[0]}


def test_each_summary_links_to_what_it_describes(rows):
    links = rows[1]
    to = lambda sid: sorted((l["target"], l["season"]) for ls in links.values() for l in ls if l["summary"] == sid)  # noqa: E731
    assert to("title:Q1") == [("Q1", None)]
    assert to("season:Q5-s2") == [("Q5", 2)]
    assert links["Character"] == [{"summary": "character:Q9@Earth-616", "target": "Q9@Earth-616", "season": None}]
    assert links["Team"] == [{"summary": "team:Avengers@Earth-616", "target": "Avengers@Earth-616", "season": None}]
    assert to("series:Q1") == [("Q1", None), ("Q3", None)]
    assert to("saga:The Infinity Saga") == [("Q1", None), ("Q3", None), ("Q5", None)]    # through its phases


def test_part_of_links_each_member_summary_to_its_group(rows):
    assert sorted((p["from"], p["to"]) for p in rows[2]) == sorted([
        ("season:Q5-s1", "title:Q5"), ("season:Q5-s2", "title:Q5"),
        ("title:Q1", "series:Q1"), ("title:Q3", "series:Q1"),
        ("title:Q1", "phase:Phase One"), ("title:Q5", "phase:Phase One"), ("title:Q3", "phase:Phase Two"),
        ("phase:Phase One", "saga:The Infinity Saga"), ("phase:Phase Two", "saga:The Infinity Saga")])


def test_nothing_loads_unless_every_summary_is_kept():
    (inp, out), (inp2, out2) = ITEMS[:2]
    assert kept([("a", inp, out, "kept", None)]) == [(inp, out)]
    with pytest.raises(RuntimeError, match=r"1 summaries are not kept: title Q3 \(check2\)"):
        kept([("a", inp, out, "kept", None), ("b", inp2, out2, "check2", None)])
