"""Unit tests for src/graph/profiles.py (profile text only; no database)."""

from src.graph.profiles import memberships_text, profile_text

WANDA = {
    "label": "Wanda Maximoff", "reality": "Earth-616",
    "aliases": ["Scarlet Witch", "Wanda Maximoff", "wanda maximoff", "Glamour"],
    "species": ["Human"],
    "actors": [{"name": "Elizabeth Olsen", "titles": 8}, {"name": "Young Actor", "titles": 1}],
    "titles": [{"title": "Avengers: Age of Ultron", "year": 2015, "order": 12},
               {"title": "Captain America: The Winter Soldier", "year": 2014, "order": 9}],
    "teams": [{"team": "Avengers", "role": "member", "status": "former"},
              {"team": "Avengers", "role": "leader", "status": "former"}],
    "variants": [{"label": "Wanda Maximoff", "reality": "Multiverse", "titles": ["What If...?"]},
                 {"label": "Wanda Maximoff", "reality": "Earth-89521", "titles": ["Marvel Zombies"]}],
}


def test_a_profile_has_one_line_per_field_in_a_fixed_order():
    assert profile_text(WANDA) == (
        "Wanda Maximoff (Earth-616). Also known as: Scarlet Witch, Glamour.\n"
        "Species: Human.\n"
        "Played by: Elizabeth Olsen (8 titles), Young Actor (1 title).\n"
        "Appears in (release order): Captain America: The Winter Soldier (2014), Avengers: Age of Ultron (2015).\n"
        "Teams: Avengers: leader (former), member (former).\n"
        "Variants: Wanda Maximoff (Earth-89521: Marvel Zombies), Wanda Maximoff (Multiverse: What If...?).")


def test_empty_fields_are_left_out():
    bare = {"label": "Bus Driver", "reality": "Earth-616", "aliases": [], "species": [], "actors": [],
            "titles": [{"title": "Iron Man", "year": 2008, "order": 1}], "teams": [], "variants": []}
    assert profile_text(bare) == "Bus Driver (Earth-616).\nAppears in (release order): Iron Man (2008)."


def test_a_variant_lists_at_most_three_titles():
    many = dict(WANDA, variants=[{"label": "Loki", "reality": "Multiverse", "titles": ["A", "B", "C", "D"]}])
    assert profile_text(many).endswith("Variants: Loki (Multiverse: A, B, C, ...).")


def test_each_role_keeps_its_own_status():
    """Nick Fury founded the Avengers and leads them now, but led them before as well: a role's
    status must stay with that role ("founder, leader; current, former" lost which was which)."""
    fury = dict(WANDA, teams=[{"team": "Avengers", "role": "leader", "status": "former"},
                              {"team": "Avengers", "role": "founder", "status": "current"},
                              {"team": "S.H.I.E.L.D.", "role": "member", "status": "former"}])
    assert "Teams: Avengers: founder (current), leader (former); S.H.I.E.L.D.: member (former)." \
        in profile_text(fury)
    assert memberships_text([{"role": "member", "status": "former"}, {"role": "member", "status": "former"}]) \
        == "member (former)"
