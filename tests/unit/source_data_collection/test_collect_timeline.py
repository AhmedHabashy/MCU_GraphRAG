"""Unit tests for src/source_data_collection/collect_timeline.py."""

from src.source_data_collection.collect_timeline import (
    mcu_wiki_rows,
    match_viewing_row,
    placement_qid,
    wikipedia_year_rows,
    years_of,
)

WIKIPEDIA_TIMELINE = """{{Marvel Cinematic Universe timeline|
{{Marvel Cinematic Universe timeline/row|year=1965–1994|break=y}}
{{Marvel Cinematic Universe timeline/row|year=1995|''[[Captain Marvel (film)|Captain Marvel]]''<ref name="x">{{Cite web|title=[[Ignored]]}}</ref>}}
{{Marvel Cinematic Universe timeline/row|year=2011|span=5
| ''[[Iron Man 2]]''<ref name="y" />
| ''[[The Incredible Hulk (film)|The Incredible Hulk]]''
}}
{{Marvel Cinematic Universe timeline/row|year=2018–2023|''[[Avengers: Endgame]]''}}
}}"""

MCU_WIKI_TABLE = """{| class="sortable"
|-
! NAME !! Dates
|-
|<center>''[[Lost and Found|Eyes of Wakanda: 1.03: Lost and Found]]''</center>
|<center>[[Before 20th Century#1400 A.D.|1400 A.D.]]</center>
|data-row-id="EoW103"|<center>August 1, 2025</center>
|<center>[[:Category:TV Series|TV Series]]</center>
|
|-
|[[File:Logo.png|center|100px]]
|<center>''[[Captain America: The First Avenger]]''</center>
|<center>[[1942|March 1942]] - [[1945|March 1, 1945]]</center>
|data-row-id="CATFA"|<center>July 22, 2011</center>
|<center>[[:Category:Movies|Film]]</center>
|
|}"""


# --- years_of -------------------------------------------------------------------------

def test_years_of_reads_single_years_ranges_and_bc():
    assert years_of("1995") == (1995, 1995)
    assert years_of("2018–2023") == (2018, 2023)
    assert years_of("March 1942 - March 1, 1945") == (1942, 1945)
    assert years_of("1400 A.D.") == (1400, 1400)
    assert years_of("1200 B.C.") == (-1200, -1200)
    assert years_of("Unknown") == (None, None)


# --- Wikipedia ------------------------------------------------------------------------

def test_wikipedia_year_rows_list_linked_titles_with_their_years_in_order():
    rows = wikipedia_year_rows(WIKIPEDIA_TIMELINE)
    assert [(r["position"], r["page"], r["start_year"], r["end_year"]) for r in rows] == [
        (1, "Captain Marvel (film)", 1995, 1995), (2, "Iron Man 2", 2011, 2011),
        (3, "The Incredible Hulk (film)", 2011, 2011), (4, "Avengers: Endgame", 2018, 2023)]


# --- MCU wiki -------------------------------------------------------------------------

def test_mcu_wiki_rows_read_the_viewing_table_in_order():
    rows = mcu_wiki_rows(MCU_WIKI_TABLE)
    assert [(r["position"], r["display"], r["dates"], r["release_date"], r["media_type"]) for r in rows] == [
        (1, "Eyes of Wakanda: 1.03: Lost and Found", "1400 A.D.", "August 1, 2025", "TV Series"),
        (2, "Captain America: The First Avenger", "March 1942 - March 1, 1945", "July 22, 2011", "Film")]


TITLES = [{"title": "Captain America: The First Avenger", "type": "Film", "wikidata_qid": "QCA", "seasons": ""},
          {"title": "Eyes of Wakanda", "type": "Animated series", "wikidata_qid": "QEOW", "seasons": ""},
          {"title": "Loki, season 1", "type": "Series season", "wikidata_qid": "QL1", "season_number": "1",
           "seasons": ""},
          {"title": "What If...?", "type": "Animated series", "wikidata_qid": "QWI", "seasons": "1|2"}]


def test_viewing_rows_match_films_by_title_and_episodes_by_show_and_season():
    assert match_viewing_row({"display": "Captain America: The First Avenger"}, TITLES) == "QCA"
    assert match_viewing_row({"display": "Eyes of Wakanda: 1.03: Lost and Found"}, TITLES) == "QEOW"
    assert match_viewing_row({"display": "Loki: 1.01: Glorious Purpose"}, TITLES) == "QL1"
    assert match_viewing_row({"display": "Loki: 2.01: Ouroboros"}, TITLES) == ""
    assert match_viewing_row({"display": "What If...?: 3.01: What If... The Hulk"}, TITLES) == ""   # out of scope
    assert match_viewing_row({"display": "Agent Carter: 1.01: Now is Not the End"}, TITLES) == ""


def season_entity(series_qid, number):
    return {"claims": {"P179": [{
        "mainsnak": {"datavalue": {"type": "wikibase-entityid", "value": {"id": series_qid}}},
        "qualifiers": {"P1545": [{"datavalue": {"type": "string", "value": str(number)}}]}}]}}


def test_placements_on_a_title_page_keep_its_qid():
    assert placement_qid("QCA", {}, TITLES) == "QCA"


def test_placements_on_a_season_page_count_for_the_series_in_scope():
    """Wikipedia places Netflix shows by season ('Daredevil season 1'); the tier list has the series."""
    entities = {"QWI3": season_entity("QWI", 2), "QWI9": season_entity("QWI", 9),
                "QX1": season_entity("QOTHER", 1)}
    assert placement_qid("QWI3", entities, TITLES) == "QWI"     # season 2 of What If...? (seasons 1|2)
    assert placement_qid("QWI9", entities, TITLES) == ""        # a season outside the tier list
    assert placement_qid("QX1", entities, TITLES) == ""         # a series not in scope


def test_a_season_page_of_a_series_with_no_season_list_counts_for_the_series():
    titles = [{"title": "Jessica Jones", "type": "Series", "wikidata_qid": "QJJ", "seasons": ""}]
    assert placement_qid("QJJ2", {"QJJ2": season_entity("QJJ", 2)}, titles) == "QJJ"
