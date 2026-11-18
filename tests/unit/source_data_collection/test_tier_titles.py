"""Unit tests for src/source_data_collection/tier_titles.py."""

import pytest

from src.source_data_collection.tier_titles import (
    SCOPE_TIERS,
    TIERS_DOC_PATH,
    load_scope_titles,
    load_tier_titles,
    read_table,
)

PLAN = """\
# Plan

### Tier 1: core for Doomsday (load first)

| Title | Type | Year | Universe |
| --- | --- | --- | --- |
| Iron Man | Film | 2008 | MCU |
| Loki, season 1 | Series | 2021 | MCU |
| What If...? (added) | Animated series | 2021-2023 | MCU |
| Thunderbolts\\* | Film | 2025 | MCU |
| Avengers: Doomsday (added) | Film | 2026 (Dec 18, upcoming) | MCU |

### Tier 2: second pass

| Title | Type | Year | Universe |
| --- | --- | --- | --- |
| Ant-Man | Film | 2015 | MCU |
"""


@pytest.fixture
def plan_path(tmp_path):
    path = tmp_path / "plan.md"
    path.write_text(PLAN, encoding="utf-8")
    return path


def test_reads_only_the_requested_tier(plan_path):
    titles = [t["title"] for t in load_tier_titles(plan_path, tier=1)]
    assert titles == ["Iron Man", "Loki, season 1", "What If...?",
                      "Thunderbolts*", "Avengers: Doomsday"]


def test_reads_a_later_tier(plan_path):
    assert [t["title"] for t in load_tier_titles(plan_path, tier=2)] == ["Ant-Man"]


def test_row_fields(plan_path):
    assert load_tier_titles(plan_path, tier=1)[0] == {
        "title": "Iron Man", "type": "Film", "year": 2008, "universe": "MCU",
        "seasons": "", "needs_review": False}


def test_year_is_first_year_of_a_range_or_annotated_value(plan_path):
    years = {t["title"]: t["year"] for t in load_tier_titles(plan_path, tier=1)}
    assert years["What If...?"] == 2021
    assert years["Avengers: Doomsday"] == 2026


def test_season_titles_get_series_season_type(plan_path):
    loki = load_tier_titles(plan_path, tier=1)[1]
    assert loki["type"] == "Series season"


def test_missing_tier_raises(plan_path):
    with pytest.raises(ValueError):
        load_tier_titles(plan_path, tier=9)


def test_optional_reality_column_is_read_by_header_name(tmp_path):
    path = tmp_path / "plan.md"
    path.write_text("### Tier 1: x\n\n| Title | Type | Year | Universe | Reality |\n"
                    "| --- | --- | --- | --- | --- |\n| Logan | Film | 2017 | Fox X-Men | Earth-17315 |\n",
                    encoding="utf-8")
    assert load_tier_titles(path, tier=1) == [{"title": "Logan", "type": "Film", "year": 2017,
                                               "universe": "Fox X-Men", "reality": "Earth-17315",
                                               "seasons": "", "needs_review": False}]


def test_review_marker_is_stripped_and_flagged(tmp_path):
    path = tmp_path / "plan.md"
    path.write_text("### Tier 1: x\n\n| Title | Type | Year | Universe | Reality |\n"
                    "| --- | --- | --- | --- | --- |\n"
                    "| Deadpool | Film | 2016 | Fox X-Men | Earth-10005 † |\n"
                    "| Logan | Film | 2017 | Fox X-Men | Earth-17315 |\n", encoding="utf-8")
    deadpool, logan = load_tier_titles(path, tier=1)
    assert deadpool["reality"] == "Earth-10005" and deadpool["needs_review"] is True
    assert logan["needs_review"] is False


def test_season_range_in_the_title_limits_a_series_to_those_seasons(tmp_path):
    path = tmp_path / "plan.md"
    path.write_text("### Tier 1: x\n\n| Title | Type | Year | Universe |\n| --- | --- | --- | --- |\n"
                    "| What If...? (added), seasons 1-2 | Animated series | 2021-2023 | MCU |\n"
                    "| Loki, season 1 | Series | 2021 | MCU |\n", encoding="utf-8")
    what_if, loki = load_tier_titles(path, tier=1)
    assert (what_if["title"], what_if["type"], what_if["seasons"]) == ("What If...?", "Animated series", "1|2")
    assert loki["seasons"] == ""


def test_read_table_reads_any_markdown_table_under_a_heading(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("## Intro\n\n### Curated roles\n\nText.\n\n| Title | Actor | Reality |\n| --- | --- | --- |\n"
                    "| Logan | Dafne Keen | Earth-17315 † |\n| * | Kerry Condon | |\n\n### Next\n",
                    encoding="utf-8")
    assert read_table(path, "### Curated roles") == [
        {"title": "Logan", "actor": "Dafne Keen", "reality": "Earth-17315", "needs_review": True},
        {"title": "*", "actor": "Kerry Condon", "reality": "", "needs_review": False}]


def test_scope_titles_are_tiers_one_and_two_with_their_tier(tmp_path):
    path = tmp_path / "plan.md"
    path.write_text("### Tier 1: a\n\n| Title | Type | Year | Universe |\n| --- | --- | --- | --- |\n"
                    "| Iron Man | Film | 2008 | MCU |\n\n"
                    "### Tier 2: b\n\n| Title | Type | Year | Universe |\n| --- | --- | --- | --- |\n"
                    "| Ant-Man | Film | 2015 | MCU |\n\n"
                    "### Tier 3: c\n\n| Title | Type | Year | Universe |\n| --- | --- | --- | --- |\n"
                    "| Venom | Film | 2018 | Sony |\n", encoding="utf-8")
    assert SCOPE_TIERS == (1, 2)
    assert [(t["title"], t["tier"]) for t in load_scope_titles(path)] == [("Iron Man", 1), ("Ant-Man", 2)]


def test_default_source_is_the_tracked_docs_file():
    assert TIERS_DOC_PATH.parts[-2:] == ("docs", "data_sources_and_tiers.md")
