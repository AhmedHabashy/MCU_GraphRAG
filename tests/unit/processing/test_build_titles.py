"""Unit tests for src/processing/build_titles.py."""

from src.processing.build_titles import (
    first_releases,
    release_order_rows,
    timeline_rows,
    title_phase_rows,
)


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


def test_a_verified_first_release_replaces_the_sources_dates():
    """Wikidata dates Jessica Jones 20 October 2015 without a source; it premiered in New York
    on 17 November (Netflix release 20 November)."""
    verified = {"Q1": "2015-11-17"}
    rows = first_releases([detail("Q1", "Jessica Jones", "2015-10-20")], {"Q1": "2015-11-20"}, verified)
    assert (rows[0]["first_release_date"], rows[0]["first_release_source"]) == ("2015-11-17", "verified")


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


def test_wikipedias_current_phase_wins_over_a_stale_wikidata_phase():
    """Ironheart moved from Phase Four to Phase Five; Wikidata still says Phase Four."""
    titles = [{"wikidata_qid": "QI", "title": "Ironheart"}, {"wikidata_qid": "QO", "title": "Only on Wikidata"}]
    wikipedia = [{"title_qid": "QI", "phase": "Phase Five"}]
    wikidata = {"QI": "Phase Four", "QO": "Phase Four"}
    rows = {r["title_qid"]: r for r in title_phase_rows(titles, wikipedia, wikidata, SAGAS)}
    assert (rows["QI"]["phases"], rows["QI"]["phase_sources"]) == ("Phase Five", "wikipedia")
    assert (rows["QO"]["phases"], rows["QO"]["phase_sources"]) == ("Phase Four", "wikidata")


# --- timeline_rows ---------------------------------------------------------------------

def test_timeline_orders_titles_by_their_first_viewing_position_and_keeps_both_sources_years():
    titles = [{"wikidata_qid": "QIM", "title": "Iron Man"}, {"wikidata_qid": "QCA", "title": "First Avenger"},
              {"wikidata_qid": "QX", "title": "X-Men"}]
    viewing = [{"position": "1", "title_qid": "QCA", "dates": "March 1942 - 1945"},
               {"position": "2", "title_qid": "", "dates": "1946"},
               {"position": "3", "title_qid": "QIM", "dates": "2010"},
               {"position": "4", "title_qid": "QCA", "dates": "2011"}]          # a later scene
    wikipedia = [{"title_qid": "QIM", "start_year": "2010", "end_year": "2010"},
                 {"title_qid": "QCA", "start_year": "1942", "end_year": "1945"}]
    rows = {r["title_qid"]: r for r in timeline_rows(titles, viewing, wikipedia)}

    assert (rows["QCA"]["chronological_order"], rows["QIM"]["chronological_order"]) == (1, 2)
    assert (rows["QCA"]["mcu_wiki_start_year"], rows["QCA"]["mcu_wiki_end_year"]) == (1942, 2011)
    assert (rows["QCA"]["wikipedia_start_year"], rows["QCA"]["wikipedia_end_year"]) == (1942, 1945)
    assert rows["QX"]["chronological_order"] == "" and rows["QX"]["wikipedia_start_year"] == ""


# --- release_order_rows ---------------------------------------------------------------

def test_release_order_sorts_by_first_release_then_title():
    rows = release_order_rows([detail("Q3", "C", "2008-04-14"), detail("Q1", "A", "2000-07-12"),
                               detail("Q2", "B", "2008-04-14")])
    assert [(r["release_order"], r["title_qid"]) for r in rows] == [(1, "Q1"), (2, "Q2"), (3, "Q3")]


def test_titles_without_a_date_are_left_out():
    rows = release_order_rows([detail("Q1", "A", ""), detail("Q2", "B", "2010-01-01")])
    assert [r["title_qid"] for r in rows] == ["Q2"]
