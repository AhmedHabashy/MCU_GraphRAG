"""Unit tests for src/processing/build_titles.py."""

from src.processing.build_titles import first_releases, release_order_rows, title_phase_rows


def detail(qid, title, date):
    return {"title_qid": qid, "title": title, "first_release_date": date}


# --- first_releases -----------------------------------------------------------------

def test_first_release_is_the_earliest_date_from_either_source():
    """TMDB records premieres that Wikidata often lacks, and sometimes the other way round."""
    wikidata = [detail("Q1", "The Avengers", "2012-04-25"), detail("Q2", "Doctor Strange", "2016-10-20")]
    tmdb = {"Q1": "2012-04-11", "Q2": "2016-10-25"}
    rows = {r["title_qid"]: r for r in first_releases(wikidata, tmdb)}
    assert (rows["Q1"]["first_release_date"], rows["Q1"]["first_release_source"]) == ("2012-04-11", "tmdb")
    assert (rows["Q2"]["first_release_date"], rows["Q2"]["first_release_source"]) == ("2016-10-20", "wikidata")


def test_same_date_in_both_sources_credits_both():
    rows = first_releases([detail("Q1", "Iron Man", "2008-04-30")], {"Q1": "2008-04-30"})
    assert rows[0]["first_release_source"] == "wikidata|tmdb"


def test_a_date_known_to_one_source_only_is_used():
    rows = first_releases([detail("Q1", "A", "")], {"Q1": "2020-01-01"})
    assert (rows[0]["first_release_date"], rows[0]["first_release_source"]) == ("2020-01-01", "tmdb")


# --- title_phase_rows -----------------------------------------------------------------

SAGAS = {"Phase Four": "The Multiverse Saga", "Phase Five": "The Multiverse Saga",
         "Phase Three": "The Infinity Saga"}


def test_title_phases_combine_both_sources_in_phase_order():
    titles = [{"wikidata_qid": "QW", "title": "What If...?"}, {"wikidata_qid": "QE", "title": "Endgame"},
              {"wikidata_qid": "QX", "title": "X-Men"}]
    wikipedia = [{"title_qid": "QW", "phase": "Phase Five"}, {"title_qid": "QW", "phase": "Phase Four"},
                 {"title_qid": "QE", "phase": "Phase Three"}]
    wikidata = {"QE": "Phase Three", "QW": "", "QX": ""}
    rows = {r["title_qid"]: r for r in title_phase_rows(titles, wikipedia, wikidata, SAGAS)}

    assert (rows["QW"]["phases"], rows["QW"]["sagas"], rows["QW"]["phase_sources"]) == \
        ("Phase Four|Phase Five", "The Multiverse Saga", "wikipedia")
    assert (rows["QE"]["phases"], rows["QE"]["sagas"], rows["QE"]["phase_sources"]) == \
        ("Phase Three", "The Infinity Saga", "wikipedia|wikidata")
    assert (rows["QX"]["phases"], rows["QX"]["sagas"]) == ("", "")


# --- release_order_rows ---------------------------------------------------------------

def test_release_order_sorts_by_first_release_then_title():
    rows = release_order_rows([detail("Q3", "C", "2008-04-14"), detail("Q1", "A", "2000-07-12"),
                               detail("Q2", "B", "2008-04-14")])
    assert [(r["release_order"], r["title_qid"]) for r in rows] == [(1, "Q1"), (2, "Q2"), (3, "Q3")]


def test_titles_without_a_date_are_left_out():
    rows = release_order_rows([detail("Q1", "A", ""), detail("Q2", "B", "2010-01-01")])
    assert [r["title_qid"] for r in rows] == ["Q2"]
