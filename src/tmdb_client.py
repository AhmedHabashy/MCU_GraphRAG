"""Client for the TMDB v3 API (credits and person external IDs)."""

from src.utils import JsonHttpClient

TMDB_API = "https://api.themoviedb.org/3"


class TmdbClient(JsonHttpClient):
    """The API key is sent as a parameter; JsonHttpClient never puts parameters in errors."""

    def __init__(self, api_key, session=None, **kwargs):
        super().__init__(session=session, **kwargs)
        self.api_key = api_key

    def _get(self, path):
        return self.get_json(f"{TMDB_API}{path}", {"api_key": self.api_key})

    def credits(self, title):
        """(path, payload) of the credits that match a registry row's type."""
        if title["type"] == "Film":
            path = f"/movie/{title['tmdb_movie_id']}/credits"
        elif title["type"] == "Series season":
            path = f"/tv/{title['tmdb_tv_id']}/season/{title['season_number']}/aggregate_credits"
        else:
            path = f"/tv/{title['tmdb_tv_id']}/aggregate_credits"
        return path, self._get(path)

    def person_external_ids(self, person_id):
        return self._get(f"/person/{person_id}/external_ids")
