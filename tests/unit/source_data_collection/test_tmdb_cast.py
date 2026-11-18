"""Unit tests for src/source_data_collection/tmdb_cast.py."""

from src.source_data_collection.tmdb_cast import (
    cast_rows,
    external_id_rows,
    merged_cast_rows,
    title_credits,
    top_billed_person_ids,
)

IRON_MAN = {"title": "Iron Man", "type": "Film", "wikidata_qid": "Q192724"}
LOKI_2 = {"title": "Loki, season 2", "type": "Series season", "wikidata_qid": "Q112610403"}

PROVENANCE = {"source": "tmdb", "retrieved_at": "t",
              "license": "TMDB API terms of use (attribution required)"}


def test_movie_credits_give_one_row_per_cast_entry():
    payload = {"cast": [{"id": 3223, "name": "Robert Downey Jr.",
                         "character": "Tony Stark", "order": 0}]}

    rows = cast_rows(IRON_MAN, "/movie/1726/credits", payload, retrieved_at="t")

    assert rows == [{
        "title": "Iron Man", "title_qid": "Q192724",
        "tmdb_person_id": "3223", "actor_name": "Robert Downey Jr.",
        "character": "Tony Stark", "billing_order": 0, "episode_count": "",
        "is_voice": False, "is_uncredited": False, "is_archive": False,
        "source_url": "https://api.themoviedb.org/3/movie/1726/credits", **PROVENANCE,
    }]


def test_aggregate_credits_give_one_row_per_role():
    payload = {"cast": [{"id": 1, "name": "Owen Wilson", "order": 1, "roles": [
        {"character": "Mobius", "episode_count": 6},
        {"character": "Don (voice)", "episode_count": 1}]}]}

    rows = cast_rows(LOKI_2, "/tv/84958/season/2/aggregate_credits", payload, retrieved_at="t")

    assert [(r["character"], r["episode_count"], r["billing_order"], r["is_voice"])
            for r in rows] == [("Mobius", 6, 1, False), ("Don (voice)", 1, 1, True)]


class FakeTmdb:
    def person_external_ids(self, person_id):
        return {"id": int(person_id), "wikidata_id": {"3223": "Q165219"}.get(person_id),
                "imdb_id": None}


def test_external_id_rows_record_tmdb_wikidata_pointer():
    rows = external_id_rows(["3223", "7"], FakeTmdb(), retrieved_at="t")
    assert [(r["tmdb_person_id"], r["wikidata_id"], r["imdb_id"]) for r in rows] == [
        ("3223", "Q165219", ""), ("7", "", "")]
    assert rows[0]["source_url"] == "https://api.themoviedb.org/3/person/3223/external_ids"


class FakeSeasonCredits:
    def __init__(self):
        self.requested = []

    def credits(self, title):
        self.requested.append(title["season_number"])
        n = title["season_number"]
        cast = [{"id": 1, "name": "Jeffrey Wright", "order": 0,
                 "roles": [{"character": "The Watcher (voice)", "episode_count": 9}]},
                {"id": int(n) + 10, "name": f"Guest {n}", "order": 1,
                 "roles": [{"character": f"Guest {n} (voice)", "episode_count": 1}]}]
        return f"/tv/91363/season/{n}/aggregate_credits", {"cast": cast}


def test_series_limited_to_seasons_is_collected_season_by_season():
    what_if = {"title": "What If...?", "type": "Animated series", "wikidata_qid": "Q65980671",
               "tmdb_tv_id": "91363", "seasons": "1|2"}
    client = FakeSeasonCredits()

    payloads = title_credits(what_if, client)

    assert client.requested == ["1", "2"]
    assert [path for path, _ in payloads] == ["/tv/91363/season/1/aggregate_credits",
                                              "/tv/91363/season/2/aggregate_credits"]


def test_cast_rows_from_several_seasons_keep_one_row_per_person_and_character():
    what_if = {"title": "What If...?", "type": "Animated series", "wikidata_qid": "Q65980671"}
    client = FakeSeasonCredits()
    payloads = [client.credits({"season_number": n}) for n in ("1", "2")]

    rows = merged_cast_rows(what_if, payloads, retrieved_at="t")

    assert [(r["actor_name"], r["character"]) for r in rows] == [
        ("Jeffrey Wright", "The Watcher (voice)"), ("Guest 1", "Guest 1 (voice)"),
        ("Guest 2", "Guest 2 (voice)")]


def test_top_billed_person_ids_are_unique_and_limited_by_billing():
    rows = [{"tmdb_person_id": "1", "billing_order": 0},
            {"tmdb_person_id": "1", "billing_order": 0},
            {"tmdb_person_id": "2", "billing_order": 9},
            {"tmdb_person_id": "3", "billing_order": 10}]
    assert top_billed_person_ids(rows, limit=10) == ["1", "2"]
