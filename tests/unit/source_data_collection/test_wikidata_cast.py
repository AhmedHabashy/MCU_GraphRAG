"""Unit tests for src/source_data_collection/wikidata_cast.py."""

from src.source_data_collection.wikidata_cast import (
    ambiguous_person_ids,
    cast_pairs,
    person_qid_rows,
    title_cast_pairs,
)


def qualified(qid, *roles):
    return {"mainsnak": {"datavalue": {"type": "wikibase-entityid", "value": {"id": qid}}},
            "qualifiers": {"P453": [
                {"datavalue": {"type": "wikibase-entityid", "value": {"id": r}}} for r in roles]}}


TITLE = {"title": "What If...?", "wikidata_qid": "Q65980671"}


def test_cast_pairs_reads_cast_and_voice_cast_with_each_character():
    entity = {"claims": {"P161": [qualified("Q1", "Q10")],
                         "P725": [qualified("Q2", "Q20", "Q21"), qualified("Q3")]}}

    pairs = cast_pairs(TITLE, entity)

    assert [(p["actor_qid"], p["character_qid"], p["property"]) for p in pairs] == [
        ("Q1", "Q10", "P161"), ("Q2", "Q20", "P725"), ("Q2", "Q21", "P725"), ("Q3", "", "P725")]
    assert pairs[0]["title_qid"] == "Q65980671"


def in_language(claim, language_qid):
    claim["qualifiers"]["P407"] = [{"datavalue": {"type": "wikibase-entityid", "value": {"id": language_qid}}}]
    return claim


def test_cast_pairs_skip_voice_actors_of_a_dub():
    """Wikidata lists the Russian dub of Spider-Man 2 as voice actors with language of work Russian."""
    entity = {"claims": {"P725": [in_language(qualified("QRU", "Q20"), "Q7737"),
                                  in_language(qualified("QEN", "Q21"), "Q1860"),
                                  qualified("QANY", "Q22")]}}

    assert [p["actor_qid"] for p in cast_pairs(TITLE, entity)] == ["QEN", "QANY"]


def test_cast_pairs_mark_their_origin():
    entity = {"claims": {"P161": [qualified("Q1", "Q10")]}}
    assert cast_pairs(TITLE, entity)[0]["via"] == ""


def test_season_also_takes_the_parent_series_cast_marked_as_such():
    season = {"title": "Loki, season 1", "wikidata_qid": "Q107185252", "type": "Series season",
              "parent_series_qid": "Q64349029"}
    entities = {"Q107185252": {"claims": {}},
                "Q64349029": {"claims": {"P161": [qualified("Q295803", "Q24046118"),
                                                  qualified("Q8", "Q107723311")]}}}

    pairs = title_cast_pairs(season, entities)

    assert [(p["title_qid"], p["actor_qid"], p["character_qid"], p["via"]) for p in pairs] == [
        ("Q107185252", "Q295803", "Q24046118", "parent_series"),
        ("Q107185252", "Q8", "Q107723311", "parent_series")]


def test_films_do_not_take_any_parent_cast():
    film = {"title": "Iron Man", "wikidata_qid": "Q192724", "type": "Film", "parent_series_qid": ""}
    entities = {"Q192724": {"claims": {"P161": [qualified("Q165219", "Q23894967")]}}}
    assert [p["via"] for p in title_cast_pairs(film, entities)] == [""]


class FakeSparqlClient:
    def __init__(self, bindings):
        self.bindings = bindings
        self.queries = []

    def sparql(self, query):
        self.queries.append(query)
        return self.bindings


def test_person_qid_rows_look_up_both_tmdb_people_and_wikidata_actors_in_batches():
    client = FakeSparqlClient([{"actor": "Q165219", "tmdb": "3223"}])

    rows = person_qid_rows(["3223", "91606", "1"], ["Q165219"], client,
                           batch_size=2, retrieved_at="t")

    assert len(client.queries) == 3  # two TMDB batches + one actor batch
    assert '"3223" "91606"' in client.queries[0] and "wdt:P4985" in client.queries[0]
    assert "wd:Q165219" in client.queries[2]
    assert rows == [{"tmdb_person_id": "3223", "actor_qid": "Q165219", "source": "wikidata",
                     "source_url": "https://www.wikidata.org/wiki/Q165219",
                     "retrieved_at": "t", "license": "CC0-1.0"}]  # duplicates removed


def test_ambiguous_person_ids_are_tmdb_people_with_several_qids():
    rows = [{"tmdb_person_id": "1", "actor_qid": "Q1"},
            {"tmdb_person_id": "2", "actor_qid": "Q2"},
            {"tmdb_person_id": "2", "actor_qid": "Q3"}]
    assert ambiguous_person_ids(rows) == ["2"]
