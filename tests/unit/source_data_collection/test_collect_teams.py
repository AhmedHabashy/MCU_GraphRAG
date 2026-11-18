"""Unit tests for src/source_data_collection/collect_teams.py."""

from src.source_data_collection.collect_teams import team_aliases, team_members

MARVEL_DB_TEAM = """{{Marvel Database:Team Template
| Name = X-Men
| Aliases = Division X{{citation}}
| Leaders = *[[Charles Xavier (Earth-10005)|Professor X]] Formerly: *[[Henry McCoy (Earth-10005)|Beast]]
| CurrentMembers = * [[Scott Summers (Earth-10005)|Cyclops]] * [[Jean Grey (Earth-10005)|Jean Grey]]
| FormerMembers = * [[Erik Lehnsherr (Earth-10005)|Magneto]]
}}"""

MCU_WIKI_TEAM = """{{Organization
| founder = [[Nick Fury]]
| leader = [[Sam Wilson]]
| members = [[Thor Odinson]]<ref>x</ref><br>[[Bruce Banner]]
| former members = [[Tony Stark]]<br>[[Steve Rogers]]
| status = Active
}}"""


def rows(members):
    return [(m["role"], m["page"], m["former"]) for m in members]


def test_marvel_database_team_template_members_and_roles():
    assert rows(team_members(MARVEL_DB_TEAM)) == [
        ("leader", "Charles Xavier (Earth-10005)", False), ("leader", "Henry McCoy (Earth-10005)", True),
        ("member", "Scott Summers (Earth-10005)", False), ("member", "Jean Grey (Earth-10005)", False),
        ("member", "Erik Lehnsherr (Earth-10005)", True)]


def test_marvel_database_organization_template_is_read_the_same_way():
    organization = MARVEL_DB_TEAM.replace("Team Template", "Organization Template")
    assert len(team_members(organization)) == 5


def test_mcu_wiki_organization_members_and_roles():
    assert rows(team_members(MCU_WIKI_TEAM)) == [
        ("founder", "Nick Fury", False), ("leader", "Sam Wilson", False),
        ("member", "Thor Odinson", False), ("member", "Bruce Banner", False),
        ("member", "Tony Stark", True), ("member", "Steve Rogers", True)]


def test_pages_without_a_team_infobox_have_no_members():
    assert team_members("{{Disambig}} Some text") == []


def test_team_aliases_from_the_marvel_database():
    wikitext = MARVEL_DB_TEAM.replace("Division X{{citation}}", "* [[Thunderbolts]]{{r|x}} * New AvengerZ")
    assert team_aliases(wikitext) == ["Thunderbolts", "New AvengerZ"]
