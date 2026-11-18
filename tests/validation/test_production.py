"""Validation of the Wikipedia production sections.

Run after collection:  .venv\\Scripts\\python.exe -m pytest -m validation
Collect with:          .venv\\Scripts\\python.exe -m src.source_data_collection.collect_production
"""

import pytest

from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.collect_production import production_path
from src.source_data_collection.storage import read_csv, read_json
from src.source_data_collection.wikitext import plain_text

pytestmark = pytest.mark.validation

MIN_WITH_SECTION = 0.95
MIN_WORDS = 200
MARKUP_LEFTOVERS = ("[[", "]]", "{{", "}}", "<ref")


@pytest.fixture(scope="module")
def records():
    titles = read_csv(REGISTRY_PATH)
    if not production_path(titles[0]["wikidata_qid"]).exists():
        pytest.skip("production sections not collected yet; run collect_production")
    return {t["wikidata_qid"]: read_json(production_path(t["wikidata_qid"])) for t in titles}


def test_almost_every_title_has_a_production_section(records):
    found = [r for r in records.values() if r["text"]]
    assert len(found) / len(records) >= MIN_WITH_SECTION, [r["title"] for r in records.values() if not r["text"]]


def test_production_sections_are_substantial(records):
    assert [(r["title"], len(r["text"].split())) for r in records.values()
            if r["text"] and len(r["text"].split()) < MIN_WORDS] == []


def test_plain_text_has_no_markup_leftovers(records):
    assert [(r["title"], m) for r in records.values() for m in MARKUP_LEFTOVERS if m in r["text"]] == []


def test_plain_text_matches_the_saved_wikitext(records):
    assert [r["title"] for r in records.values() if r["text"] != plain_text(r["wikitext"])] == []


def test_records_have_provenance(records):
    assert [r["title"] for r in records.values() if r["text"]
            and not (r["revid"] and r["source_url"] and r["license"] and r["retrieved_at"])] == []
