"""Unit tests for src/source_data_collection/build_title_registry.py (fake client, no network)."""

from src.source_data_collection.build_title_registry import (
    ALLOWED_INSTANCE_OF,
    build_rows,
    enwiki_candidates,
)


def item(qid):
    return {"mainsnak": {"datavalue": {"type": "wikibase-entityid", "value": {"id": qid}}}}


def string(value):
    return {"mainsnak": {"datavalue": {"type": "string", "value": value}}}


def date(time):
    return {"mainsnak": {"datavalue": {"type": "time", "value": {"time": time}}}}


def entity(qid, label, instance_of, year=None, **ids):
    claims = {"P31": [item(i) for i in instance_of]}
    if year:
        claims["P577"] = [date(f"+{year}-05-02T00:00:00Z")]
    for pid, value in ids.items():
        claims[pid] = [string(value)]
    return {"id": qid, "labels": {"en": {"value": label}}, "claims": claims}


def page(qid, title, disambiguation=False, missing=False):
    return {"resolved_title": title, "qid": qid,
            "is_disambiguation": disambiguation, "missing": missing}


class FakeClient:
    def __init__(self, pages, entities):
        self.pages = pages
        self.entities = entities

    def resolve_enwiki_titles(self, titles):
        return {t: self.pages.get(t, page(None, t, missing=True)) for t in titles}

    def get_entities(self, ids):
        return {q: self.entities[q] for q in ids if q in self.entities}


IRON_MAN = {"title": "Iron Man", "type": "Film", "year": 2008, "universe": "MCU"}
IRON_MAN_2008 = entity("Q192724", "Iron Man", ["Q11424"], 2008,
                       P4947="1726", P345="tt0371746")


# --- enwiki_candidates ------------------------------------------------------

def test_film_candidates_try_year_then_film_then_bare_title():
    assert enwiki_candidates(IRON_MAN) == [
        "Iron Man (2008 film)", "Iron Man (film)", "Iron Man"]


def test_tv_specials_are_looked_up_like_films():
    title = {"title": "Werewolf by Night", "type": "Special", "year": 2022}
    assert enwiki_candidates(title) == ["Werewolf by Night (2022 film)", "Werewolf by Night (film)",
                                        "Werewolf by Night"]


def test_tier2_types_are_accepted():
    assert "Q1261214" in ALLOWED_INSTANCE_OF["Special"]              # television special
    assert "Q113791292" in ALLOWED_INSTANCE_OF["Animated shorts"]    # animated short film series


def test_series_candidates_try_tv_series_disambiguators_then_bare_title():
    title = {"title": "What If...?", "type": "Animated series", "year": 2021}
    assert enwiki_candidates(title) == [
        "What If...? (TV series)", "What If...? (2021 TV series)", "What If...?"]


def test_season_candidate_drops_the_comma():
    title = {"title": "Loki, season 1", "type": "Series season", "year": 2021}
    assert enwiki_candidates(title) == ["Loki season 1"]


# --- build_rows: candidate selection ------------------------------------------

def test_build_rows_picks_first_candidate_matching_type_and_year():
    client = FakeClient(
        pages={"Iron Man (2008 film)": page("Q192724", "Iron Man (2008 film)"),
               "Iron Man": page("Q180704", "Iron Man")},
        entities={"Q192724": IRON_MAN_2008,
                  "Q180704": entity("Q180704", "Iron Man", ["Q1114461"])})

    rows, raw = build_rows([IRON_MAN], client, retrieved_at="2026-11-17T00:00:00Z")

    assert rows == [{
        **IRON_MAN,
        "enwiki_title": "Iron Man (2008 film)",
        "wikidata_qid": "Q192724",
        "wikidata_label": "Iron Man",
        "wikidata_year": 2008,
        "instance_of": "Q11424",
        "tmdb_movie_id": "1726",
        "tmdb_tv_id": "",
        "imdb_id": "tt0371746",
        "wikidata_year_from": "item",
        "parent_series_qid": "",
        "season_number": "",
        "source": "wikidata",
        "source_url": "https://www.wikidata.org/wiki/Q192724",
        "retrieved_at": "2026-11-17T00:00:00Z",
        "license": "CC0-1.0",
    }]
    assert raw == {"Q192724": IRON_MAN_2008}


def test_build_rows_skips_candidate_with_wrong_year():
    remake = entity("Q999", "Iron Man", ["Q11424"], 2030)
    client = FakeClient(
        pages={"Iron Man (2008 film)": page(None, "Iron Man (2008 film)", missing=True),
               "Iron Man (film)": page("Q999", "Iron Man (film)"),
               "Iron Man": page("Q192724", "Iron Man")},
        entities={"Q999": remake, "Q192724": IRON_MAN_2008})

    rows, _ = build_rows([IRON_MAN], client, retrieved_at="t")

    assert rows[0]["wikidata_qid"] == "Q192724"


def test_build_rows_skips_disambiguation_pages():
    client = FakeClient(
        pages={"Iron Man (film)": page("Q1", "Iron Man (film)", disambiguation=True),
               "Iron Man": page("Q192724", "Iron Man")},
        entities={"Q1": entity("Q1", "Iron Man", ["Q11424"], 2008),
                  "Q192724": IRON_MAN_2008})

    rows, _ = build_rows([IRON_MAN], client, retrieved_at="t")

    assert rows[0]["wikidata_qid"] == "Q192724"


def test_build_rows_accepts_matching_type_when_wikidata_has_no_date():
    loki = {"title": "Loki, season 2", "type": "Series season", "year": 2023}
    client = FakeClient(
        pages={"Loki season 2": page("Q112610403", "Loki season 2")},
        entities={"Q112610403": entity("Q112610403", "Loki, season 2", ["Q3464665"])})

    rows, _ = build_rows([loki], client, retrieved_at="t")

    assert rows[0]["wikidata_qid"] == "Q112610403"
    assert rows[0]["wikidata_year"] == ""


def test_build_rows_keeps_unresolved_title_with_blank_fields():
    rows, raw = build_rows([IRON_MAN], FakeClient(pages={}, entities={}), retrieved_at="t")

    assert rows[0]["wikidata_qid"] == ""
    assert rows[0]["enwiki_title"] == ""
    assert rows[0]["source_url"] == ""
    assert rows[0]["wikidata_year_from"] == ""
    assert raw == {}


# --- build_rows: TV seasons ---------------------------------------------------

LOKI = entity("Q64349029", "Loki", ["Q5398426"], 2021, P4983="84958", P345="tt9140554")


def season(qid, number, year=None, episodes=()):
    season_entity = entity(qid, f"Loki, season {number}", ["Q3464665"], year)
    season_entity["claims"]["P179"] = [{
        **item("Q64349029"),
        "qualifiers": {"P1545": [{"datavalue": {"type": "string", "value": str(number)}}]}}]
    season_entity["claims"]["P527"] = [item(e) for e in episodes]
    return season_entity


def episode(qid, time):
    return {"id": qid, "claims": {"P577": [date(time)]}}


def test_season_takes_crosswalk_ids_from_parent_series():
    loki1 = {"title": "Loki, season 1", "type": "Series season", "year": 2021}
    client = FakeClient(pages={"Loki season 1": page("Q107185252", "Loki season 1")},
                        entities={"Q107185252": season("Q107185252", 1, year=2021),
                                  "Q64349029": LOKI})

    rows, raw = build_rows([loki1], client, retrieved_at="t")

    assert rows[0]["parent_series_qid"] == "Q64349029"
    assert rows[0]["season_number"] == "1"
    assert rows[0]["tmdb_tv_id"] == "84958"
    assert rows[0]["imdb_id"] == "tt9140554"
    assert rows[0]["wikidata_year_from"] == "item"
    assert set(raw) == {"Q107185252", "Q64349029"}


def test_undated_season_takes_year_from_earliest_episode():
    loki2 = {"title": "Loki, season 2", "type": "Series season", "year": 2023}
    episodes = {"Q1": episode("Q1", "+2023-10-12T00:00:00Z"),
                "Q2": episode("Q2", "+2023-10-05T00:00:00Z")}
    client = FakeClient(
        pages={"Loki season 2": page("Q112610403", "Loki season 2")},
        entities={"Q112610403": season("Q112610403", 2, episodes=["Q1", "Q2"]),
                  "Q64349029": LOKI, **episodes})

    rows, raw = build_rows([loki2], client, retrieved_at="t")

    assert rows[0]["wikidata_year"] == 2023
    assert rows[0]["wikidata_year_from"] == "episodes"
    assert {"Q1", "Q2"} <= set(raw)


def test_build_rows_joins_multiple_values_with_pipe():
    both = entity("Q192724", "Iron Man", ["Q11424", "Q115768274"], 2008)
    client = FakeClient(pages={"Iron Man (2008 film)": page("Q192724", "Iron Man (2008 film)")},
                        entities={"Q192724": both})

    rows, _ = build_rows([IRON_MAN], client, retrieved_at="t")

    assert rows[0]["instance_of"] == "Q11424|Q115768274"
