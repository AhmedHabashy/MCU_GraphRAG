"""Unit tests for src/source_data_collection/wikidata_cast.py."""

from src.source_data_collection.wikidata_cast import (
    ambiguous_person_ids,
    cast_pairs,
    person_qid_rows,
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
