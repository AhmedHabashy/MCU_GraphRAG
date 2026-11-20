"""Unit tests for src/source_data_collection/collect_title_details.py."""

from src.source_data_collection.collect_title_details import (
    first_release,
    sequel_links,
    sequel_series,
    title_detail_row,
    tmdb_crew_rows,
)


def item(qid, qualifiers=None):
    claim = {"mainsnak": {"datavalue": {"type": "wikibase-entityid", "value": {"id": qid}}}}
    if qualifiers:
        claim["qualifiers"] = {p: [{"datavalue": {"type": "wikibase-entityid", "value": {"id": q}}}]
                               for p, q in qualifiers.items()}
    return claim


def date(time, rank="normal"):
    return {"mainsnak": {"datavalue": {"type": "time", "value": {"time": time, "precision": 11}}},
            "rank": rank}


IRON_MAN = {"id": "Q192724", "claims": {
    "P57": [item("Q295964")], "P58": [item("Q1"), item("Q2")],
    "P577": [date("+2008-05-02T00:00:00Z", "preferred"), date("+2008-04-14T00:00:00Z")],
    "P840": [item("Q889")],
    "P179": [item("Q16642701", {"P156": "Q205028"})]}}   # the Iron Man film series
LABELS = {"Q295964": "Jon Favreau", "Q1": "Mark Fergus", "Q2": "Hawk Ostby",
          "Q889": "Afghanistan", "Q205028": "Iron Man 2"}


# --- first_release ----------------------------------------------------------------------

def test_first_release_is_the_earliest_date_including_premieres():
    assert first_release(IRON_MAN, episodes=[]) == ("2008-04-14", "item")


def test_series_without_its_own_date_uses_its_earliest_episode():
    episodes = [{"claims": {"P577": [date("+2023-10-12T00:00:00Z")]}},
                {"claims": {"P577": [date("+2023-10-05T00:00:00Z")]}}]
    assert first_release({"claims": {}}, episodes) == ("2023-10-05", "episodes")


def test_an_earlier_episode_date_wins_over_the_items_own():
    episodes = [{"claims": {"P577": [date("+2021-06-09T00:00:00Z")]}}]
    season = {"claims": {"P577": [date("+2021-06-10T00:00:00Z")]}}
    assert first_release(season, episodes) == ("2021-06-09", "episodes")


def test_no_dates_give_blanks():
    assert first_release({"claims": {}}, []) == ("", "")


# --- sequel_links -----------------------------------------------------------------------

def test_sequel_links_come_from_the_ordering_within_a_sequel_series():
    """X-Men Origins: Wikidata's direct 'follows' wrongly says First Class, its series says Last Stand."""
    entity = {"claims": {"P155": [item("QFirstClass")],
                         "P179": [item("QXMenSeries", {"P155": "QLastStand", "P156": "QFirstClass"})]}}
    assert sequel_links(entity, {"QXMenSeries"}) == (["QLastStand"], ["QFirstClass"])


def test_release_order_in_a_franchise_or_direct_claims_is_not_a_sequel():
    """Ant-Man 'follows' Age of Ultron in the MCU franchise item; Jessica Jones 'follows' Daredevil
    by a direct claim. Both are release order, not sequels."""
    ant_man = {"claims": {"P179": [item("QMCU", {"P155": "QAgeOfUltron"}), item("QAntManSeries")]}}
    jessica_jones = {"claims": {"P155": [item("QDaredevil")]}}
    assert sequel_links(ant_man, {"QAntManSeries"}) == ([], [])
    assert sequel_links(jessica_jones, set()) == ([], [])


def series(qid, kinds, parts=(), part_of=()):
    return qid, {"claims": {"P31": [item(k) for k in kinds], "P527": [item(p) for p in parts],
                            "P361": [item(p) for p in part_of]}}


def test_sequel_series_are_the_most_specific_film_or_tv_series():
    entities = dict([
        series("QIronMan", ["Q24856", "Q149010"]),                      # film series, trilogy
        series("QPhaseOne", ["Q24856", "Q431289"]),                     # film series, but a brand
        series("QMCU", ["Q196600", "Q3275581"]),                        # franchise, shared universe
        series("QXMen", ["Q24856"], parts=["QXMenTrilogy"]),            # umbrella of a kept series
        series("QXMenTrilogy", ["Q13593818"]),                          # film trilogy
        series("QLoki", ["Q5398426"]),                                  # television series
        series("QPortrayal", ["Q138337574"]),                           # 'Spider-Man in film'
        series("QWolverine", ["Q24856"], part_of=["QXMen"]),
    ])
    assert sequel_series(entities) == {"QIronMan", "QXMenTrilogy", "QLoki", "QWolverine"}


# --- title_detail_row -------------------------------------------------------------------

def test_title_detail_row_flattens_people_dates_locations_and_sequels():
    title = {"title": "Iron Man", "wikidata_qid": "Q192724", "type": "Film"}
    row = title_detail_row(title, IRON_MAN, [], LABELS, {"Q16642701"}, retrieved_at="t")
    assert row == {
        "title": "Iron Man", "title_qid": "Q192724", "type": "Film",
        "director_qids": "Q295964", "director_names": "Jon Favreau",
        "writer_qids": "Q1|Q2", "writer_names": "Mark Fergus|Hawk Ostby",
        "first_release_date": "2008-04-14", "first_release_from": "item",
        "follows_qids": "", "follows_names": "",
        "followed_by_qids": "Q205028", "followed_by_names": "Iron Man 2",
        "location_qids": "Q889", "location_names": "Afghanistan",
        "source": "wikidata", "source_url": "https://www.wikidata.org/wiki/Q192724",
        "retrieved_at": "t", "license": "CC0-1.0",
    }


# --- tmdb_crew_rows -----------------------------------------------------------------------

def test_tmdb_crew_rows_keep_directors_and_writers_from_saved_credits():
    saved = {"title": "Iron Man", "source_url": "https://api.themoviedb.org/3/movie/1726/credits",
             "retrieved_at": "t", "license": "TMDB",
             "response": {"crew": [
                 {"id": 15277, "name": "Jon Favreau", "job": "Director", "department": "Directing"},
                 {"id": 9, "name": "Mark Fergus", "job": "Screenplay", "department": "Writing"},
                 {"id": 8, "name": "Someone", "job": "Editor", "department": "Editing"}]}}
    rows = tmdb_crew_rows("Q192724", saved)
    assert [(r["tmdb_person_id"], r["name"], r["role"]) for r in rows] == [
        ("15277", "Jon Favreau", "director"), ("9", "Mark Fergus", "writer")]
    assert rows[0]["source_url"] == "https://api.themoviedb.org/3/movie/1726/credits"


def test_tmdb_crew_rows_read_aggregate_tv_jobs():
    saved = {"title": "X", "source_url": "u", "retrieved_at": "t", "license": "TMDB",
             "response": {"crew": [{"id": 5, "name": "Kate Herron", "department": "Directing",
                                    "jobs": [{"job": "Director"}]}]}}
    assert [r["role"] for r in tmdb_crew_rows("Q1", saved)] == ["director"]
