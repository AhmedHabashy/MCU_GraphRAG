"""Unit tests for src/source_data_collection/incremental.py."""

from src.source_data_collection.incremental import (
    TitleScopes,
    collection_scope,
    in_title_order,
    saved_or_fetched,
    stored_rows,
)
from src.source_data_collection.storage import write_csv

JJ = {"title": "Jessica Jones", "type": "Series", "wikidata_qid": "QJJ", "enwiki_title": "Jessica Jones (TV series)",
      "seasons": "1|2", "season_number": "", "tmdb_movie_id": "", "tmdb_tv_id": "38472", "year": "2015"}
IRON_MAN = {"title": "Iron Man", "type": "Film", "wikidata_qid": "QIM", "enwiki_title": "Iron Man (2008 film)",
            "seasons": "", "season_number": "", "tmdb_movie_id": "1726", "tmdb_tv_id": "", "year": "2008"}


def test_scope_is_what_decides_what_is_fetched_for_a_title():
    assert collection_scope({**JJ, "year": "2016"}) == collection_scope(JJ)
    assert collection_scope({**JJ, "seasons": "1|2|3"}) != collection_scope(JJ)


def test_nothing_collected_yet_means_every_title_is_collected(tmp_path):
    assert TitleScopes("plots", tmp_path).to_collect([JJ, IRON_MAN]) == [JJ, IRON_MAN]


def test_only_new_or_changed_titles_are_collected_again(tmp_path):
    TitleScopes("plots", tmp_path).save([JJ, IRON_MAN])
    jj3 = {**JJ, "seasons": "1|2|3"}
    new = {**IRON_MAN, "title": "Iron Man 2", "wikidata_qid": "QIM2"}

    assert TitleScopes("plots", tmp_path).to_collect([jj3, IRON_MAN, new]) == [jj3, new]


def test_saving_forgets_titles_no_longer_in_scope(tmp_path):
    TitleScopes("plots", tmp_path).save([JJ, IRON_MAN])
    TitleScopes("plots", tmp_path).save([IRON_MAN])
    assert TitleScopes("plots", tmp_path).to_collect([JJ, IRON_MAN]) == [JJ]


def test_each_collector_keeps_its_own_scopes(tmp_path):
    TitleScopes("plots", tmp_path).save([JJ])
    assert TitleScopes("production", tmp_path).to_collect([JJ]) == [JJ]


def test_stored_rows_keeps_only_the_wanted_keys(tmp_path):
    path = tmp_path / "cast.csv"
    write_csv(path, [{"title_qid": "QJJ", "actor": "Krysten Ritter"},
                     {"title_qid": "QIM", "actor": "Robert Downey Jr."}])
    assert stored_rows(path, {"QIM"}) == [{"title_qid": "QIM", "actor": "Robert Downey Jr."}]
    assert stored_rows(tmp_path / "missing.csv", {"QIM"}) == []


def test_stored_rows_by_another_key(tmp_path):
    path = tmp_path / "people.csv"
    write_csv(path, [{"tmdb_person_id": "3223", "wikidata_id": "Q165219"}])
    assert stored_rows(path, {"3223"}, key="tmdb_person_id") == [{"tmdb_person_id": "3223", "wikidata_id": "Q165219"}]


def test_rows_are_put_back_in_title_order():
    rows = [{"title_qid": "QJJ", "n": 1}, {"title_qid": "QIM", "n": 2}, {"title_qid": "QJJ", "n": 3}]
    assert [r["n"] for r in in_title_order(rows, [IRON_MAN, JJ])] == [2, 1, 3]


def test_a_saved_page_is_read_back_and_a_new_one_fetched_once(tmp_path):
    calls = []

    def fetch():
        calls.append(1)
        return {"page": "Time Variance Authority", "retrieved_at": "now"}

    path = tmp_path / "TVA.json"
    assert saved_or_fetched(path, fetch) == {"page": "Time Variance Authority", "retrieved_at": "now"}
    assert saved_or_fetched(path, fetch)["page"] == "Time Variance Authority"
    assert calls == [1]


def test_a_missing_page_is_not_saved(tmp_path):
    path = tmp_path / "Missing.json"
    assert saved_or_fetched(path, lambda: None) is None and not path.exists()
