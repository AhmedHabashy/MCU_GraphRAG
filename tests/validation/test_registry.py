"""Validation of source_data/wikidata/titles.csv (Tiers 1 and 2) against the acceptance criteria.

Run after collection:  .venv\\Scripts\\python.exe -m pytest -m validation
"""

import csv
import re

import pytest

from src.source_data_collection.build_title_registry import (
    ALLOWED_INSTANCE_OF, P_HAS_PARTS, P_IMDB_ID, P_INSTANCE_OF, P_PART_OF_THE_SERIES,
    P_SERIES_ORDINAL, P_TMDB_MOVIE_ID, P_TMDB_TV_ID, REGISTRY_PATH, SEASON,
)
from src.source_data_collection.tier_titles import load_scope_titles, load_tier_titles
from src.utils import P_PUBLICATION_DATE, P_START_TIME, WikimediaClient, label

pytestmark = pytest.mark.validation

EXPECTED_TIER1_COUNT = 49
EXPECTED_TIER2_COUNT = 28   # I Am Groot's two seasons are one title
EXPECTED_TIER3_COUNT = 21

TMDB_FIELD_BY_TYPE = {"Film": "tmdb_movie_id", "Special": "tmdb_movie_id", "Series": "tmdb_tv_id",
                      "Animated series": "tmdb_tv_id", "Animated shorts": "tmdb_tv_id",
                      SEASON: "tmdb_tv_id"}
PROVENANCE_FIELDS = ["source", "source_url", "retrieved_at", "license"]

EXPECTED_PROPERTY_LABELS = {
    P_INSTANCE_OF: "instance of",
    P_PUBLICATION_DATE: "publication date",
    P_START_TIME: "start time",
    P_TMDB_MOVIE_ID: "TMDB movie ID",
    P_TMDB_TV_ID: "TMDB TV series ID",
    P_IMDB_ID: "IMDb ID",
    P_PART_OF_THE_SERIES: "part of the series",
    P_SERIES_ORDINAL: "series ordinal",
    P_HAS_PARTS: "has part(s)",
}


@pytest.fixture(scope="module")
def rows():
    if not REGISTRY_PATH.exists():
        pytest.skip(f"{REGISTRY_PATH} not collected yet; "
                    "run src.source_data_collection.build_title_registry")
    with open(REGISTRY_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def seasons(rows):
    return [r for r in rows if r["type"] == SEASON]


# Scope decisions from the MCU expert.

def test_every_tier1_reality_is_confirmed():
    assert [t["title"] for t in load_tier_titles(tier=1) if t["needs_review"]] == []


def test_what_if_is_limited_to_seasons_one_and_two():
    what_if = next(t for t in load_tier_titles(tier=1) if t["title"] == "What If...?")
    assert what_if["seasons"] == "1|2"


def test_netflix_daredevil_and_punisher_are_in_tier_2():
    tier2 = {t["title"] for t in load_tier_titles(tier=2)}
    tier3 = {t["title"] for t in load_tier_titles(tier=3)}
    assert {"Daredevil", "The Punisher"} <= tier2 and not {"Daredevil", "The Punisher"} & tier3


# Check 1: every tier title resolved, no blanks, no duplicates.

def test_docs_list_every_title_in_scope():
    assert len(load_tier_titles(tier=1)) == EXPECTED_TIER1_COUNT
    assert len(load_tier_titles(tier=2)) == EXPECTED_TIER2_COUNT
    assert len(load_tier_titles(tier=3)) == EXPECTED_TIER3_COUNT


def test_registry_has_one_row_per_tier_title(rows):
    assert [(r["title"], r["tier"]) for r in rows] == [(t["title"], str(t["tier"])) for t in load_scope_titles()]


def test_every_title_has_a_qid(rows):
    assert [r["title"] for r in rows if not r["wikidata_qid"]] == []


def test_qids_are_unique(rows):
    qids = [r["wikidata_qid"] for r in rows]
    assert sorted({q for q in qids if qids.count(q) > 1}) == []


# Check 2: label, type and year agree with the tier list.

def test_every_qid_has_a_label(rows):
    assert [r["title"] for r in rows if not r["wikidata_label"]] == []


def test_instance_of_matches_tier_type(rows):
    assert [(r["title"], r["instance_of"]) for r in rows
            if not set(r["instance_of"].split("|")) & ALLOWED_INSTANCE_OF[r["type"]]] == []


def test_wikidata_year_matches_tier_year(rows):
    assert [(r["title"], r["wikidata_year"]) for r in rows
            if r["wikidata_year"] != r["year"]] == []


def test_every_year_records_where_it_came_from(rows):
    assert [r["title"] for r in rows
            if r["wikidata_year_from"] not in {"item", "episodes"}] == []


# Check 3: crosswalk IDs present.

def test_every_title_has_its_tmdb_id(rows):
    assert [r["title"] for r in rows if not r[TMDB_FIELD_BY_TYPE[r["type"]]]] == []


def test_every_title_has_exactly_one_imdb_id(rows):
    assert [(r["title"], r["imdb_id"]) for r in rows
            if not r["imdb_id"] or "|" in r["imdb_id"]] == []


# Seasons: linked to their parent series with the right season number.

def test_seasons_have_a_parent_series(seasons):
    assert seasons and [r["title"] for r in seasons if not r["parent_series_qid"]] == []


def test_season_number_matches_title(seasons):
    assert [(r["title"], r["season_number"]) for r in seasons
            if r["season_number"] != re.search(r"season (\d+)$", r["title"]).group(1)] == []


def test_non_seasons_have_no_parent_series(rows):
    assert [r["title"] for r in rows
            if r["type"] != SEASON and (r["parent_series_qid"] or r["season_number"])] == []


# Check 4: each title is tied to a real Wikipedia article
# (missing and disambiguation pages are rejected during candidate selection).

def test_every_title_has_an_enwiki_article(rows):
    assert [r["title"] for r in rows if not r["enwiki_title"]] == []


# Provenance: every record stores source, source_url, retrieved_at, license.

def test_every_row_has_provenance(rows):
    assert [(r["title"], f) for r in rows for f in PROVENANCE_FIELDS if not r[f]] == []


# Check 5: the Wikidata property IDs used in code mean what we think (live call).

def test_property_ids_have_expected_labels():
    entities = WikimediaClient().get_entities(list(EXPECTED_PROPERTY_LABELS), props="labels")
    actual = {pid: label(entities[pid]) for pid in EXPECTED_PROPERTY_LABELS}
    assert actual == EXPECTED_PROPERTY_LABELS
