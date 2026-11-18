"""Unit tests for src/source_data_collection/collect_production.py."""

from src.source_data_collection.collect_production import PRODUCTION_HEADINGS, production_record

TITLE = {"title": "Iron Man", "wikidata_qid": "Q192724", "enwiki_title": "Iron Man (2008 film)"}


class FakeClient:
    def __init__(self, section):
        self.section, self.prefixes = section, None

    def top_level_section(self, page, prefix):
        self.prefixes = prefix
        return self.section


def test_production_record_keeps_wikitext_plain_text_and_revision():
    section = {"page": "Iron Man (2008 film)", "revid": 7, "heading": "Production", "index": "3",
               "wikitext": "== Production ==\nBased on [[Iron Man|the comic]]{{efn|x}} by Stan Lee."}
    client = FakeClient(section)

    record = production_record(TITLE, client, retrieved_at="t")

    assert client.prefixes == PRODUCTION_HEADINGS == ("Production", "Development")
    assert record["text"] == "Based on the comic by Stan Lee."
    assert (record["revid"], record["heading"], record["title_qid"]) == (7, "Production", "Q192724")
    assert record["source_url"] == "https://en.wikipedia.org/wiki/Iron_Man_(2008_film)"
    assert record["license"] == "CC BY-SA 4.0"


def test_missing_section_gives_an_empty_record():
    record = production_record(TITLE, FakeClient(None), retrieved_at="t")
    assert record["text"] == "" and record["heading"] == ""
