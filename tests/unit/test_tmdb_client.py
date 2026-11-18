"""Unit tests for src/tmdb_client.py (fake session, no network)."""

from src.tmdb_client import TMDB_API, TmdbClient
from tests.unit.test_utils import FakeResponse, FakeSession


def make_client(payload=None):
    session = FakeSession([FakeResponse(200, payload=payload or {"cast": []})])
    return TmdbClient(api_key="KEY", session=session, sleep=lambda _s: None), session


def test_film_uses_movie_credits():
    client, session = make_client()
    path, _ = client.credits({"type": "Film", "tmdb_movie_id": "1726"})
    assert path == "/movie/1726/credits"
    assert session.calls[0] == (f"{TMDB_API}/movie/1726/credits", {"api_key": "KEY"})


def test_series_uses_aggregate_credits():
    client, _ = make_client()
    path, _ = client.credits({"type": "Animated series", "tmdb_tv_id": "91363"})
    assert path == "/tv/91363/aggregate_credits"


def test_season_uses_season_aggregate_credits():
    client, _ = make_client()
    path, _ = client.credits({"type": "Series season", "tmdb_tv_id": "84958",
                              "season_number": "2"})
    assert path == "/tv/84958/season/2/aggregate_credits"


def test_film_first_release_is_the_earliest_date_of_any_country_and_type():
    payload = {"results": [
        {"iso_3166_1": "US", "release_dates": [{"release_date": "2008-05-02T00:00:00.000Z", "type": 3}]},
        {"iso_3166_1": "AU", "release_dates": [{"release_date": "2008-04-30T00:00:00.000Z", "type": 3},
                                               {"release_date": "2008-04-14T00:00:00.000Z", "type": 1}]}]}
    client, session = make_client(payload)
    path, date = client.first_release({"type": "Film", "tmdb_movie_id": "1726"})
    assert (path, date) == ("/movie/1726/release_dates", "2008-04-14")


def test_series_first_release_is_its_first_air_date():
    client, _ = make_client({"first_air_date": "2021-08-11"})
    assert client.first_release({"type": "Animated series", "tmdb_tv_id": "91363"}) == \
        ("/tv/91363", "2021-08-11")


def test_season_first_release_is_the_season_air_date():
    client, _ = make_client({"air_date": "2023-10-05"})
    assert client.first_release({"type": "Series season", "tmdb_tv_id": "84958",
                                 "season_number": "2"}) == ("/tv/84958/season/2", "2023-10-05")


def test_missing_dates_are_blank():
    client, _ = make_client({"first_air_date": None})
    assert client.first_release({"type": "Series", "tmdb_tv_id": "1"})[1] == ""


def test_person_details():
    client, session = make_client({"id": 3223, "birthday": "1965-04-04"})
    assert client.person("3223")["birthday"] == "1965-04-04"
    assert session.calls[0][0] == f"{TMDB_API}/person/3223"


def test_person_external_ids():
    client, session = make_client({"id": 3223, "wikidata_id": "Q165219"})
    assert client.person_external_ids("3223")["wikidata_id"] == "Q165219"
    assert session.calls[0][0] == f"{TMDB_API}/person/3223/external_ids"
