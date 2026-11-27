"""Unit tests for the pure parts of global search, DRIFT and the aggregation tool (no database)."""

from src.retrieval.aggregate import VIEWS, closest_views, view_block
from src.retrieval.global_search import summary_block, summary_ids


def test_named_summaries_come_first_then_the_searched_ones_once_each():
    named = [{"kind": "Group", "key": "saga:The Infinity Saga"}, {"kind": "Title", "key": "Q1"},
             {"kind": "Person", "key": "Q9"}, {"kind": "Character", "key": "C1@Earth-616"}]
    assert summary_ids(named, ["title:Q1", "phase:Phase One"]) == [
        "saga:The Infinity Saga", "title:Q1", "character:C1@Earth-616", "phase:Phase One"]
    assert summary_ids([], [f"title:Q{i}" for i in range(20)], limit=3) == ["title:Q0", "title:Q1", "title:Q2"]


def test_a_summary_block_gives_the_text_the_key_facts_and_last_the_titles():
    row = {"kind": "phase", "name": "Phase One", "text": "Tony builds a suit.", "facts": ["Tony is Iron Man."],
           "cites": ["[Q1]"], "titles": [{"title": "Iron Man", "qid": "Q1", "type": "Film", "year": 2008,
                                          "first_release_date": "2008-04-30", "start_year": 2008, "end_year": 2008,
                                          "universe": "MCU", "phases": ["Phase One"]}]}
    assert summary_block(row).split("\n") == [
        "## Summary (phase): Phase One", "Tony builds a suit.", "Key facts:", "- Tony is Iron Man. [Q1]",
        "Titles (1, in release order):",
        "- Iron Man [Q1] (Film, released 2008-04-30; set 2008 to 2008; universe MCU; phases: Phase One)"]


def test_the_closest_views_are_those_with_the_highest_scores():
    assert closest_views({"a": 0.2, "b": 0.9, "c": 0.5}, shown=2) == ["b", "c"]


def test_a_view_block_says_over_how_many_rows_it_is_computed():
    rows = [{"name": "Anthony Russo", "count": 5, "titles": ["Civil War", "Endgame"]}]
    assert view_block("directors", rows).split("\n") == [
        "## The 20 directors of the most films, counted over all films:",
        "- Anthony Russo: 5 films: Civil War, Endgame"]
    assert view_block("phases", [{"phase": "no phase", "count": 2, "titles": ["Logan", "X2"]}]).split("\n")[1] == \
        "- no phase: 2 titles: Logan, X2"


def test_every_view_has_a_description_a_query_a_header_and_a_line():
    assert all({"description", "query", "header", "line"} <= set(v) for v in VIEWS.values())
