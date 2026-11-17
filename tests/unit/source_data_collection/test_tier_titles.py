"""Unit tests for src/source_data_collection/tier_titles.py."""

import pytest

from src.source_data_collection.tier_titles import TIERS_DOC_PATH, load_tier_titles

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
        "title": "Iron Man", "type": "Film", "year": 2008, "universe": "MCU"}


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


def test_default_source_is_the_tracked_docs_file():
    assert TIERS_DOC_PATH.parts[-2:] == ("docs", "data_sources_and_tiers.md")
