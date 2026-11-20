"""Validation of teams and memberships: MCU wiki vs Marvel Database, linked to characters.

Run after building:  .venv\\Scripts\\python.exe -m pytest -m validation
Build with:          .venv\\Scripts\\python.exe -m src.source_data_collection.collect_teams
                     .venv\\Scripts\\python.exe -m src.processing.build_teams
"""

import pytest

from src.processing.build_characters import PERFORMANCES_PATH
from src.processing.build_teams import MEMBERSHIPS_PATH, TEAMS_PATH, team_id
from src.source_data_collection.collect_teams import load_teams
from src.source_data_collection.storage import read_csv

pytestmark = pytest.mark.validation

MIN_MEMBERS_LINKED = 0.80
MIN_SOURCE_AGREEMENT = 0.70


def _load(path):
    if not path.exists():
        pytest.skip(f"{path} not built yet; run collect_teams and build_teams")
    return read_csv(path)


@pytest.fixture(scope="module")
def teams():
    return {t["team_id"]: t for t in _load(TEAMS_PATH)}


@pytest.fixture(scope="module")
def memberships(teams):
    return _load(MEMBERSHIPS_PATH)


@pytest.fixture(scope="module")
def performances():
    return read_csv(PERFORMANCES_PATH)


def role_of(performances, title_qid, actor):
    found = {p["character_id"] for p in performances
             if p["title_qid"] == title_qid and p["actor_name"] == actor and p["character_id"]}
    assert len(found) == 1, (title_qid, actor, found)
    return next(iter(found))


def member(memberships, team, character_id, role="member", status=None):
    return any(m["team_id"] == team and m["character_id"] == character_id and m["role"] == role
               and (status is None or m["status"] == status) for m in memberships)


# --- Coverage --------------------------------------------------------------------------

def test_every_curated_team_was_built(teams):
    assert sorted({team_id(t["team"], t["reality"]) for t in load_teams()} - set(teams)) == []


def test_every_team_has_members(teams, memberships):
    assert [t for t in teams if not any(m["team_id"] == t and m["role"] == "member" for m in memberships)] == []


def test_most_members_link_to_a_character(memberships):
    linked = [m for m in memberships if m["character_id"]]
    assert len(linked) / len(memberships) >= MIN_MEMBERS_LINKED, \
        [(m["team_id"], m["member_page"]) for m in memberships if not m["character_id"]]


# --- MCU wiki vs Marvel Database ---------------------------------------------------------

def test_the_wikis_agree_on_team_members(teams, memberships):
    """Of the members the MCU wiki lists, most are also listed by the Marvel Database. Teams
    only: for an organization (S.H.I.E.L.D., HYDRA) each wiki lists its own selection of
    hundreds of members (the Marvel Database's S.H.I.E.L.D. has no Maria Hill, the MCU wiki's
    lists minor Agents of S.H.I.E.L.D. agents), so the lists are not expected to agree."""
    by_source = {}
    for m in memberships:
        if m["character_id"] and teams[m["team_id"]]["kind"] == "team":
            by_source.setdefault((m["team_id"], m["source"]), set()).add(m["character_id"])
    low = []
    for (team, source), members in by_source.items():
        other = by_source.get((team, "marvel"))
        if source == "marvelcinematicuniverse" and other:
            share = len(members & other) / len(members)
            if share < MIN_SOURCE_AGREEMENT:
                low.append((team, round(share, 2), sorted(members - other)))
    assert low == []


# --- Spot checks (MCU expert's teams) ------------------------------------------------------

def test_avengers(memberships, performances):
    team = "Avengers@Earth-616"
    assert member(memberships, team, role_of(performances, "Q192724", "Robert Downey Jr."), status="former")
    assert member(memberships, team, role_of(performances, "Q22665878", "Chris Hemsworth"))


def test_new_avengers_are_the_thunderbolts(teams, memberships, performances):
    team = "New Avengers@Earth-616"
    assert "Thunderbolts" in teams[team]["aliases"].split("|")
    assert member(memberships, team, role_of(performances, "Q112322474", "Florence Pugh"), role="leader")
    assert member(memberships, team, role_of(performances, "Q112322474", "Sebastian Stan"))


def test_fantastic_four_is_led_by_the_first_steps_reed_richards(memberships, performances):
    reed = role_of(performances, "Q105105219", "Pedro Pascal")
    assert member(memberships, "Fantastic Four@Earth-828", reed, role="leader")


def test_fox_x_men(memberships, performances):
    team = "X-Men@Earth-10005"
    assert member(memberships, team, role_of(performances, "Q106182", "Patrick Stewart"), role="leader")
    assert member(memberships, team, role_of(performances, "Q106182", "Ian McKellen"), status="former")


def test_illuminati_include_captain_carter(memberships, performances):
    carter = role_of(performances, "Q64211112", "Hayley Atwell")
    assert member(memberships, "Illuminati@Earth-838", carter, status="former")


def test_every_row_is_a_team_or_an_organization(teams):
    assert {t["kind"] for t in teams.values()} == {"team", "organization"}


def test_round_3_organizations(teams):
    """MCU expert, round 3: S.H.I.E.L.D. is an organization, as are HYDRA and the Hand."""
    assert [t for t in ("S.H.I.E.L.D.@Earth-616", "HYDRA@Earth-616", "The Hand@Earth-616")
            if teams[t]["kind"] != "organization"] == []
    assert teams["Defenders@Earth-616"]["kind"] == "team"


def test_defenders(memberships, performances):
    team = "Defenders@Earth-616"
    assert member(memberships, team, role_of(performances, "Q16977365", "Charlie Cox"))
    assert member(memberships, team, role_of(performances, "Q18605540", "Krysten Ritter"))


def test_hydra_was_led_by_the_red_skull(memberships, performances):
    red_skull = role_of(performances, "Q275120", "Hugo Weaving")
    assert any(m["team_id"] == "HYDRA@Earth-616" and m["character_id"] == red_skull for m in memberships)


@pytest.mark.parametrize("member_name, impostor", [
    ("R. Keller", "Q66189316@Earth-616"),    # Talos posed as Director Keller
    ("James Davis", "mcuwiki:Izel@Earth-616"),  # Izel posed as Agent Davis
])
def test_members_are_not_linked_to_someone_who_posed_as_them(memberships, member_name, impostor):
    rows = [m for m in memberships if m["member_name"] == member_name or m["member_page"] == member_name]
    assert rows and impostor not in {m["character_id"] for m in rows}


def test_daisy_johnson_is_in_shield(memberships):
    """Expert, round 4: link Daisy Johnson to S.H.I.E.L.D. (and to the Inhumans: her species)."""
    assert member(memberships, "S.H.I.E.L.D.@Earth-616", "Q24027972@Earth-616")


def test_rows_have_provenance(memberships):
    assert [m for m in memberships if not (m["source"] and m["source_url"] and m["revid"])] == []
