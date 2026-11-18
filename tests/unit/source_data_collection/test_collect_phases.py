"""Unit tests for src/source_data_collection/collect_phases.py."""

import pytest

from src.source_data_collection.collect_phases import (
    phase_headings,
    phase_name,
    titles_in_heading,
    wikidata_phases,
)

TITLES = [{"title": "Iron Man", "type": "Film", "wikidata_qid": "Q192724", "seasons": ""},
          {"title": "Deadpool & Wolverine", "type": "Film", "wikidata_qid": "Q102180106", "seasons": ""},
          {"title": "Loki, season 1", "type": "Series season", "wikidata_qid": "QL1", "season_number": "1",
           "seasons": ""},
          {"title": "Loki, season 2", "type": "Series season", "wikidata_qid": "QL2", "season_number": "2",
           "seasons": ""},
          {"title": "What If...?", "type": "Animated series", "wikidata_qid": "QW", "seasons": "1|2"},
          {"title": "The Falcon and the Winter Soldier", "type": "Series", "wikidata_qid": "QF", "seasons": ""}]


@pytest.mark.parametrize("heading, expected", [
    ("<i>Iron Man</i> (2008)", ["Q192724"]),
    ("<i>Deadpool &amp; Wolverine</i> (2024)", ["Q102180106"]),
    ("<i>Loki</i> season 1 (2021)", ["QL1"]),
    ("<i>Loki</i> season 2 (2023)", ["QL2"]),
    ("<i>What If...?</i> season 1 (2021)", ["QW"]),
    ("<i>What If...?</i> seasons 2 and 3 (2023–24)", ["QW"]),         # season 2 is in scope
    ("<i>The Falcon and the Winter Soldier</i> (2021)", ["QF"]),
    ("<i>Eternals</i> (2021)", []),                                     # not a Tier 1 title
])
def test_titles_in_heading(heading, expected):
    assert titles_in_heading(heading, TITLES) == expected


def test_what_if_season_three_alone_is_out_of_scope():
    assert titles_in_heading("<i>What If...?</i> season 3 (2024)", TITLES) == []


def test_phase_headings_are_the_subsections_of_film_and_television_sections():
    sections = [{"toclevel": 1, "line": "Development"}, {"toclevel": 2, "line": "Background"},
                {"toclevel": 1, "line": "Films"}, {"toclevel": 2, "line": "<i>Iron Man</i> (2008)"},
                {"toclevel": 3, "line": "Plot"},
                {"toclevel": 1, "line": "Television series"}, {"toclevel": 2, "line": "<i>Loki</i> season 1 (2021)"},
                {"toclevel": 1, "line": "Music"}, {"toclevel": 2, "line": "Soundtrack"}]
    assert phase_headings(sections) == ["<i>Iron Man</i> (2008)", "<i>Loki</i> season 1 (2021)"]


def test_phase_name_from_a_wikidata_label():
    assert phase_name("Marvel Cinematic Universe Phase Three") == "Phase Three"
    assert phase_name("The Infinity Saga") == ""


def item(qid):
    return {"mainsnak": {"datavalue": {"type": "wikibase-entityid", "value": {"id": qid}}}}


def test_wikidata_phases_and_sagas_from_part_of_the_series():
    entity = {"claims": {"P179": [item("QMCU"), item("QP3"), item("QSAGA")]}}
    labels = {"QMCU": "Marvel Cinematic Universe", "QP3": "Marvel Cinematic Universe Phase Three",
              "QSAGA": "The Infinity Saga"}
    assert wikidata_phases(entity, labels) == (["Phase Three"], ["The Infinity Saga"])
