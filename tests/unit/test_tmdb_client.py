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


def test_person_external_ids():
    client, session = make_client({"id": 3223, "wikidata_id": "Q165219"})
    assert client.person_external_ids("3223")["wikidata_id"] == "Q165219"
    assert session.calls[0][0] == f"{TMDB_API}/person/3223/external_ids"
