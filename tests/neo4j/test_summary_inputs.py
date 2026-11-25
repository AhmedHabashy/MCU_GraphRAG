"""Checks on the summary inputs built from the loaded graph (src.graph.summary_inputs).

Run with:  .venv\\Scripts\\python.exe -m pytest -m neo4j
"""

import pytest

from src.graph.summary_inputs import build, citations, group_inputs, read_plots, series_chains
from tests.neo4j.test_graph import count, db  # noqa: F401  (the db fixture)

pytestmark = pytest.mark.neo4j


@pytest.fixture(scope="module")
def session(db):  # noqa: F811
    if not count(db, "MATCH (c:Character) WHERE c.profile IS NOT NULL RETURN count(c) AS n"):
        pytest.skip("profiles not written; run src.graph.profiles")
    from src.graph.neo4j_db import connect
    with connect() as driver, driver.session() as s:
        yield s


@pytest.fixture(scope="module")
def plots():
    return read_plots()


@pytest.fixture(scope="module")
def level1(session, plots):
    built, waiting = build(session, plots, outputs={})
    return built, waiting


def test_level_one_has_every_title_main_character_and_team_and_the_rest_waits(level1):
    built, waiting = level1
    kinds = {}
    for i in built:
        kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
    # Agents of S.H.I.E.L.D. (7 seasons), Daredevil and Jessica Jones (3 each) are split by season
    assert kinds == {"title": 95, "season": 13, "character": 391, "team": 12}
    assert waiting == {"title": 3, "series": 18, "phase": 6, "universe": 10, "saga": 2, "reality": 2}
    assert {i["name"] for i in built if i["kind"] == "season"} >= {
        "Agents of S.H.I.E.L.D., season 7", "Daredevil, season 3", "Jessica Jones, season 1"}


def test_no_input_is_over_the_size_limit(level1):
    from src.graph.summary_inputs import MAX_INPUT_CHARS
    assert [i["name"] for i in level1[0] if len(i["text"]) > MAX_INPUT_CHARS] == []


def test_every_citation_names_a_real_title_and_episode(level1, plots):
    episodes = {q: {e["number_overall"] for e in p.get("episodes") or []} for q, p in plots.items()}
    for inp in level1[0]:
        for qid, ep in citations(inp["text"]):
            assert qid in plots, (inp["id"], qid)
            assert ep is None or ep in episodes[qid], (inp["id"], qid, ep)


def test_a_character_input_is_its_profile_and_its_plot_facts(level1):
    sylvie = next(i for i in level1[0] if i["kind"] == "character" and i["name"] == "Sylvie")
    profile, facts = sylvie["text"].split("\n\nPlot facts (release order):\n")
    assert profile.startswith("Sylvie (")
    assert "KILLS He Who Remains" in facts and "[Q107185252 ep 6]" in facts


def test_upper_levels_take_their_members_from_the_summaries_below(session, plots):
    titles = [r.data() for r in session.run(
        "MATCH (t:Title) RETURN t.qid AS qid, t.title AS title, t.universe AS universe, t.reality AS reality, "
        "t.phases AS phases, t.sagas AS sagas, t.release_order AS release_order")]
    stub = {("title", t["qid"]): {"name": t["title"], "summary": "s", "key_facts": []} for t in titles}
    stub.update({("phase", p): {"name": p, "summary": "s", "key_facts": []} for t in titles for p in t["phases"]})
    stub.update({("universe", t["universe"]): {"name": t["universe"], "summary": "s", "key_facts": []}
                 for t in titles})
    items = {(k, i): inp for k, i, inp in group_inputs(titles, series_chains(session), stub)}
    phase_one = items[("phase", "Phase One")]
    assert [next(t["title"] for t in titles if t["qid"] == q) for q in phase_one["sources"]] == [
        "Iron Man", "The Incredible Hulk", "Iron Man 2", "Thor", "Captain America: The First Avenger", "The Avengers"]
    assert items[("saga", "The Infinity Saga")]["sources"] == ["Phase One", "Phase Two", "Phase Three"]
    # Logan (Earth-17315) keeps the Fox X-Men universe from lying wholly in Earth-10005, so Earth-10005 is
    # written from its own titles: the 12 Fox films there and Deadpool & Wolverine
    earth_10005 = {next(t["title"] for t in titles if t["qid"] == q) for q in items[("reality", "Earth-10005")]["sources"]}
    assert len(earth_10005) == 13 and "Deadpool & Wolverine" in earth_10005 and "Logan" not in earth_10005
    # Earth-616 takes the Netflix, Marvel TV and ABC universes whole, and the MCU's titles one by one
    earth_616 = items[("reality", "Earth-616")]["sources"]
    assert {"Netflix", "Marvel TV", "ABC"} <= set(earth_616) and "MCU" not in earth_616
