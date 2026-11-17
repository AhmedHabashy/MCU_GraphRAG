"""Unit tests for src/source_data_collection/collect_characters.py."""

from src.source_data_collection.collect_characters import (
    character_qids,
    character_row,
    earth_of,
    marvel_db_page,
    marvel_db_row,
)


def item(qid):
    return {"mainsnak": {"datavalue": {"type": "wikibase-entityid", "value": {"id": qid}}}}


def string(value):
    return {"mainsnak": {"datavalue": {"type": "string", "value": value}}}


def monolingual(text):
    return {"mainsnak": {"datavalue": {"type": "monolingualtext",
                                       "value": {"text": text, "language": "en"}}}}


LOKI = {"id": "Q24046118",
        "labels": {"en": {"value": "Loki"}},
        "aliases": {"en": [{"value": "Loki Laufeyson"}, {"value": "God of Mischief"}]},
        "claims": {"P1080": [item("Q642878")], "P144": [item("Q1147326")],
                   "P1889": [item("Q107723311")], "P460": [item("Q1147326")],
                   "P175": [item("Q295803")], "P742": [monolingual("Loki of Asgard")],
                   "P6262": [string("marvelcinematicuniverse:Loki"),
                             string("marvel:Loki_Laufeyson_(Earth-199999)")]}}
RELATED = {"Q642878": {"labels": {"en": {"value": "Marvel Cinematic Universe"}},
                       "claims": {"P6262": [string("marvel:Earth-199999")]}},
           "Q1147326": {"labels": {"en": {"value": "Loki"}}, "claims": {}},
           "Q107723311": {"labels": {"en": {"value": "Sylvie"}}, "claims": {}}}


def test_character_qids_are_unique_and_skip_the_generic_self_item():
    rows = [{"character_qid": "Q1"}, {"character_qid": ""}, {"character_qid": "Q18086706"},
            {"character_qid": "Q1"}, {"character_qid": "Q2"}]
    assert character_qids(rows) == ["Q1", "Q2"]


def test_marvel_db_page_picks_the_english_marvel_database_article():
    assert marvel_db_page(LOKI) == "Loki Laufeyson (Earth-199999)"
    assert marvel_db_page({"claims": {}}) == ""


def test_earth_of_reads_the_reality_from_a_page_title():
    assert earth_of("Loki Laufeyson (Earth-199999)") == "Earth-199999"
    assert earth_of("James Howlett (Earth-TRN414)") == "Earth-TRN414"
    assert earth_of("Mojo") == ""


def test_character_row_flattens_names_universes_and_variant_links():
    row = character_row(LOKI, RELATED, retrieved_at="t")

    assert row["character_qid"] == "Q24046118" and row["label"] == "Loki"
    assert row["aliases"] == "Loki Laufeyson|God of Mischief"
    assert row["pseudonyms"] == "Loki of Asgard"
    assert row["universe_qids"] == "Q642878"
    assert row["universe_earths"] == "Earth-199999"
    assert row["based_on_qids"] == "Q1147326" and row["based_on_labels"] == "Loki"
    assert row["same_as_qids"] == "Q1147326"
    assert row["different_from_labels"] == "Sylvie"
    assert row["performer_qids"] == "Q295803"
    assert row["marvel_db_page"] == "Loki Laufeyson (Earth-199999)"
    assert row["source_url"] == "https://www.wikidata.org/wiki/Q24046118"
    assert row["license"] == "CC0-1.0"


def test_marvel_db_row_parses_the_character_infobox():
    lead = {"page": "Anthony Stark (Earth-199999)", "revid": 11251179,
            "url": "https://marvel.fandom.com/wiki/Anthony_Stark_(Earth-199999)",
            "wikitext": "{{Marvel Database:Character Template\n"
                        "| Name = [[Tony Stark|Anthony Edward \"Tony\" Stark]]\n"
                        "| CurrentAlias = Iron Man\n| Codenames = Shellhead\n"
                        "| Aliases = * Howard Potts{{r|x}} * The Mechanic\n"
                        "| Reality = [[Earth-199999]]\n"
                        "| Affiliation = Formerly: * {{m|Avengers}} * {{m|Stark Industries}}\n}}"}

    row = marvel_db_row("Q23894967", lead, retrieved_at="t")

    assert row["name"] == 'Anthony Edward "Tony" Stark'
    assert row["current_alias"] == "Iron Man"
    assert row["other_names"] == "Shellhead|Howard Potts|The Mechanic"
    assert row["reality"] == "Earth-199999"
    assert row["affiliations"] == "Avengers|Stark Industries"
    assert row["revid"] == 11251179
    assert row["source"] == "marvel_database"


def test_marvel_db_row_for_a_missing_page_keeps_the_qid_and_blanks():
    row = marvel_db_row("Q1", None, retrieved_at="t", page="Nope (Earth-1)")
    assert row["character_qid"] == "Q1" and row["page"] == "Nope (Earth-1)" and row["revid"] == ""
    assert row["source_url"] == "https://marvel.fandom.com/wiki/Nope_(Earth-1)"  # what was tried
    assert row["fetched"] is False


def test_marvel_db_row_marks_fetched_pages():
    lead = {"page": "X (Earth-1)", "revid": 5, "url": "https://marvel.fandom.com/wiki/X_(Earth-1)",
            "wikitext": ""}
    assert marvel_db_row("Q1", lead, retrieved_at="t")["fetched"] is True
