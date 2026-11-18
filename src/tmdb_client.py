"""Client for the TMDB v3 API (credits and person external IDs)."""

from src.title_types import SEASON, is_movie
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
        if is_movie(title):
            path = f"/movie/{title['tmdb_movie_id']}/credits"
        elif title["type"] == SEASON:
            path = f"/tv/{title['tmdb_tv_id']}/season/{title['season_number']}/aggregate_credits"
        else:
            path = f"/tv/{title['tmdb_tv_id']}/aggregate_credits"
        return path, self._get(path)

    def first_release(self, title):
        """(path, 'YYYY-MM-DD') of a title's first release: a film's earliest date of any
        country and release type (premieres included), a series' or season's first air date."""
        if is_movie(title):
            path = f"/movie/{title['tmdb_movie_id']}/release_dates"
            dates = [d["release_date"][:10] for country in self._get(path)["results"]
                     for d in country["release_dates"] if d.get("release_date")]
            return path, min(dates, default="")
        if title["type"] == SEASON:
            path = f"/tv/{title['tmdb_tv_id']}/season/{title['season_number']}"
            return path, self._get(path).get("air_date") or ""
        path = f"/tv/{title['tmdb_tv_id']}"
        return path, self._get(path).get("first_air_date") or ""

    def details(self, title):
        """(path, payload) of a film's, series' or season's details."""
        if is_movie(title):
            path = f"/movie/{title['tmdb_movie_id']}"
        elif title["type"] == SEASON:
            path = f"/tv/{title['tmdb_tv_id']}/season/{title['season_number']}"
        else:
            path = f"/tv/{title['tmdb_tv_id']}"
        return path, self._get(path)

    def person(self, person_id):
        return self._get(f"/person/{person_id}")

    def person_external_ids(self, person_id):
        return self._get(f"/person/{person_id}/external_ids")
