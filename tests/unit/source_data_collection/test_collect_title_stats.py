"""Unit tests for src/source_data_collection/collect_title_stats.py."""

from src.source_data_collection.collect_title_stats import tmdb_stats_row, wikidata_money_row

IRON_MAN = {"title": "Iron Man", "type": "Film", "wikidata_qid": "Q192724"}


def test_film_stats_from_tmdb_details():
    payload = {"budget": 140000000, "revenue": 585174222, "runtime": 126, "vote_average": 7.65,
               "vote_count": 27000, "popularity": 30.1,
               "genres": [{"name": "Action"}, {"name": "Science Fiction"}],
               "production_companies": [{"name": "Marvel Studios"}]}
    row = tmdb_stats_row(IRON_MAN, "/movie/1726", payload, series_genres=[], retrieved_at="t")
    assert row == {"title": "Iron Man", "title_qid": "Q192724", "type": "Film",
                   "budget_usd": 140000000, "revenue_usd": 585174222, "runtime_minutes": 126,
                   "vote_average": 7.65, "vote_count": 27000, "popularity": 30.1,
                   "genres": "Action|Science Fiction", "production_companies": "Marvel Studios",
                   "source": "tmdb", "source_url": "https://api.themoviedb.org/3/movie/1726",
                   "retrieved_at": "t", "license": "TMDB API terms of use (attribution required)"}


def test_tv_special_runtime_comes_from_its_movie_details():
    special = {"title": "Werewolf by Night", "type": "Special", "wikidata_qid": "Q111426635"}
    row = tmdb_stats_row(special, "/movie/894205", {"runtime": 53}, series_genres=[], retrieved_at="t")
    assert row["runtime_minutes"] == 53


def test_unknown_money_is_blank_not_zero():
    row = tmdb_stats_row(IRON_MAN, "/movie/1", {"budget": 0, "revenue": 0, "runtime": 0},
                         series_genres=[], retrieved_at="t")
    assert (row["budget_usd"], row["revenue_usd"], row["runtime_minutes"]) == ("", "", "")


def test_series_runtime_is_the_typical_episode_length():
    series = {"title": "Loki", "type": "Series", "wikidata_qid": "Q1"}
    row = tmdb_stats_row(series, "/tv/1", {"episode_run_time": [52, 48, 50], "genres": [{"name": "Drama"}]},
                         series_genres=[], retrieved_at="t")
    assert row["runtime_minutes"] == 50 and row["genres"] == "Drama"


def test_season_runtime_from_its_episodes_and_genres_from_the_series():
    season = {"title": "Loki, season 1", "type": "Series season", "wikidata_qid": "Q2"}
    payload = {"vote_average": 8.0, "episodes": [{"runtime": 51}, {"runtime": 47}, {"runtime": None}]}
    row = tmdb_stats_row(season, "/tv/84958/season/1", payload,
                         series_genres=["Drama", "Sci-Fi & Fantasy"], retrieved_at="t")
    assert row["runtime_minutes"] == 49 and row["genres"] == "Drama|Sci-Fi & Fantasy"


def test_season_vote_count_is_the_sum_of_its_episode_votes():
    """TMDB's season endpoint has an average rating but no vote count; its episodes have both."""
    season = {"title": "Loki, season 1", "type": "Series season", "wikidata_qid": "Q2"}
    payload = {"vote_average": 8.0, "episodes": [{"runtime": 50, "vote_count": 300},
                                                 {"runtime": 50, "vote_count": 250}]}
    row = tmdb_stats_row(season, "/tv/84958/season/1", payload, series_genres=["Drama"], retrieved_at="t")
    assert row["vote_count"] == 550


def quantity(amount, unit):
    return {"mainsnak": {"datavalue": {"type": "quantity", "value": {
        "amount": amount, "unit": f"http://www.wikidata.org/entity/{unit}"}}}, "rank": "normal"}


def test_wikidata_money_takes_the_largest_us_dollar_figures_and_minutes():
    entity = {"claims": {"P2142": [quantity("+318412101", "Q4917"), quantity("+585174222", "Q4917"),
                                   quantity("+900000000", "Q25224")],          # pounds: ignored
                         "P2130": [quantity("+140000000", "Q4917")],
                         "P2047": [quantity("+126", "Q7727"), quantity("+2", "Q25235")]}}   # hours: ignored
    row = wikidata_money_row(IRON_MAN, entity, retrieved_at="t")
    assert (row["box_office_usd"], row["cost_usd"], row["duration_minutes"]) == (585174222, 140000000, 126)
    assert row["source_url"] == "https://www.wikidata.org/wiki/Q192724"


def test_wikidata_money_is_blank_when_missing():
    row = wikidata_money_row(IRON_MAN, {"claims": {}}, retrieved_at="t")
    assert (row["box_office_usd"], row["cost_usd"], row["duration_minutes"]) == ("", "", "")
