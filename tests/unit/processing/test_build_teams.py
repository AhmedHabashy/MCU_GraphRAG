"""Unit tests for src/processing/build_teams.py."""

from src.processing.build_teams import membership_rows, resolve_member, team_id, team_rows

CHARACTERS = [
    {"character_id": "Q23894967@Earth-616", "reality": "Earth-616", "label": "Tony Stark",
     "marvel_db_page": "Anthony Stark (Earth-199999)", "mcu_wiki_page": "Iron Man"},
    {"character_id": "Q24046102@Earth-616", "reality": "Earth-616", "label": "Thor",
     "marvel_db_page": "", "mcu_wiki_page": "Thor Odinson"},
    {"character_id": "Q105350971@Earth-10005", "reality": "Earth-10005", "label": "Charles Xavier",
     "marvel_db_page": "", "mcu_wiki_page": ""},
    {"character_id": "Q105350971@Earth-838", "reality": "Earth-838", "label": "Professor X",
     "marvel_db_page": "", "mcu_wiki_page": ""},
    {"character_id": "QB@Earth-31393", "reality": "Earth-31393", "label": "Bishop",
     "marvel_db_page": "Lucas Bishop (Earth-31393)", "mcu_wiki_page": ""},
]
ALIASES = {"Q105350971@Earth-10005": {"charles xavier", "professor x"},
           "Q105350971@Earth-838": {"charles xavier", "professor x"},
           "Q24046102@Earth-616": {"thor", "thor odinson"}}


def member(page, name, source="marvel", role="member", former=False):
    return {"page": page, "name": name, "source": source, "role": role, "former": str(former)}


def resolve(m, reality):
    return resolve_member(m, reality, CHARACTERS, ALIASES)


def test_members_resolve_by_marvel_database_page():
    assert resolve(member("Anthony Stark (Earth-199999)", "Iron Man"), "Earth-616") == \
        ("Q23894967@Earth-616", "marvel_db_page")


def test_members_resolve_by_mcu_wiki_page():
    assert resolve(member("Thor Odinson", "Thor Odinson", "marvelcinematicuniverse"), "Earth-616") == \
        ("Q24046102@Earth-616", "mcu_wiki_page")


def test_members_resolve_by_name_within_the_team_reality_only():
    assert resolve(member("Charles Xavier (Earth-10005)", "Professor X"), "Earth-10005") == \
        ("Q105350971@Earth-10005", "name")
    assert resolve(member("Charles Xavier (Earth-838)", "Professor Xavier"), "Earth-838") == \
        ("Q105350971@Earth-838", "name")


NETFLIX = [{"character_id": "QIF@Earth-616", "reality": "Earth-616", "label": "Iron Fist",
            "marvel_db_page": "", "mcu_wiki_page": ""},
           {"character_id": "mcuwiki:Davos@Earth-616", "reality": "Earth-616", "label": "Davos",
            "marvel_db_page": "", "mcu_wiki_page": "Davos"},
           {"character_id": "QJJ@Earth-616", "reality": "Earth-616", "label": "Jessica Jones",
            "marvel_db_page": "", "mcu_wiki_page": ""},
           {"character_id": "QPW@Earth-616", "reality": "Earth-616", "label": "Patsy Walker",
            "marvel_db_page": "", "mcu_wiki_page": ""}]
NETFLIX_ALIASES = {"QIF@Earth-616": {"iron fist", "daniel rand", "danny rand"},
                   "mcuwiki:Davos@Earth-616": {"davos", "iron fist"},
                   "QJJ@Earth-616": {"jessica jones"},
                   "QPW@Earth-616": {"patsy walker", "trish walker", "jessica jones"}}


def test_the_page_name_is_tried_before_a_shared_codename():
    """'Iron Fist' is also Davos; 'Daniel Rand' (the page) is only Danny."""
    assert resolve_member(member("Daniel Rand (Earth-199999)", "Iron Fist"), "Earth-616", NETFLIX,
                          NETFLIX_ALIASES) == ("QIF@Earth-616", "name")


def test_a_name_several_characters_share_goes_to_the_one_it_labels():
    assert resolve_member(member("Jessica Jones (Earth-199999)", "Jessica Jones"), "Earth-616", NETFLIX,
                          NETFLIX_ALIASES) == ("QJJ@Earth-616", "name")


def test_a_name_shared_with_no_label_match_stays_unresolved():
    aliases = {**NETFLIX_ALIASES, "QJJ@Earth-616": {"jessica jones", "trish walker"}}
    assert resolve_member(member("Trish Walker", "Trish Walker", "marvelcinematicuniverse"), "Earth-616",
                          NETFLIX, aliases) == ("", "")


def test_a_member_from_another_reality_resolves_by_page():
    assert resolve(member("Lucas Bishop (Earth-31393)", "Bishop"), "Earth-92131") == \
        ("QB@Earth-31393", "marvel_db_page")


def test_unknown_members_stay_unresolved():
    assert resolve(member("Sean Cassidy (Earth-10005)", "Banshee"), "Earth-10005") == ("", "")


def test_team_ids_and_rows_include_curated_and_wiki_aliases():
    teams = [{"team": "New Avengers", "reality": "Earth-616", "kind": "team", "also called": "Thunderbolts"}]
    aliases = [{"team": "New Avengers", "reality": "Earth-616", "alias": "New AvengerZ", "source": "marvel"}]
    assert team_id("New Avengers", "Earth-616") == "New Avengers@Earth-616"
    [row] = team_rows(teams, aliases)
    assert (row["team_id"], row["aliases"]) == ("New Avengers@Earth-616", "Thunderbolts|New AvengerZ")


def test_team_rows_keep_the_kind():
    """S.H.I.E.L.D. is an organization, not a team (MCU expert, round 3)."""
    teams = [{"team": "S.H.I.E.L.D.", "reality": "Earth-616", "kind": "organization", "also called": ""}]
    assert team_rows(teams, [])[0]["kind"] == "organization"


def test_membership_rows_record_status_role_and_resolution():
    members = [{"team": "X-Men", "reality": "Earth-10005", **member("Charles Xavier (Earth-10005)", "Professor X",
                                                                     role="leader")},
               {"team": "X-Men", "reality": "Earth-10005", **member("Sean Cassidy (Earth-10005)", "Banshee",
                                                                     former=True)}]
    rows = membership_rows(members, CHARACTERS, ALIASES)
    assert [(r["team_id"], r["character_id"], r["role"], r["status"], r["resolved_by"]) for r in rows] == [
        ("X-Men@Earth-10005", "Q105350971@Earth-10005", "leader", "current", "name"),
        ("X-Men@Earth-10005", "", "member", "former", "")]
