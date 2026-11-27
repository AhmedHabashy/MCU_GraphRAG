"""Unit tests for the pure parts of src/retrieval/board.py (no database)."""

from src.retrieval.board import card, chosen, evidence, linked, links


def entry(kind, key, name):
    return {"kind": kind, "key": key, "names": [name], "weight": 1}


def test_the_question_cards_come_first_then_one_per_name_from_the_answer():
    question = [entry("Character", "C1@Earth-616", "Peggy Carter"), entry("Character", "C1@Earth-838", "Captain Carter")]
    answer = [entry("Character", "C1@Earth-616", "Peggy Carter"), entry("Person", "P1", "Hayley Atwell"),
              entry("Person", "P2", "Hayley Atwell"), entry("Group", "phase:Phase Four", "Phase Four")]
    assert [c["key"] for c in chosen(question, answer)] == ["C1@Earth-616", "C1@Earth-838", "P1"]
    assert len(chosen(question, answer, max_cards=1)) == 1


def test_a_card_names_what_it_is_and_the_line_under_its_name():
    row = {"id": "4:1", "label": "Logan", "reality": None, "type": "Film", "year": 2017, "team_kind": None}
    assert card("Title", row) == {"id": "4:1", "kind": "title", "label": "Logan", "under": "Film, 2017"}
    assert card("Character", dict(row, label="Logan", reality="Earth-17315"))["under"] == "Earth-17315"
    assert card("Thing", dict(row, label="Earth-616", type="universe", reality="Earth-10005"))["under"] == "universe"


def row(**kw):
    base = {"source": "a", "target": "b", "type": "PLAYS", "source_name": "", "evidence": None, "title": "Logan",
            "credited": [], "role": None, "status": None, "shared": None}
    return dict(base, **kw)


def test_each_relationship_gives_its_own_kind_of_evidence():
    assert evidence(row(credited=["Logan"])) == "cast of Logan, credited as Logan"
    assert evidence(row(type="KILLS", source_name="plot", evidence="X-24 kills Charles")) == 'Logan: "X-24 kills Charles"'
    assert evidence(row(type="MEMBER_OF", source_name="marvel", role="leader", status="former")) == "leader, former (marvel wiki)"
    assert evidence(row(type="VARIANT_OF", shared="Q1")) == "Wikidata shared identity Q1"


def test_rows_of_one_direction_and_kind_make_one_link_naming_every_type():
    rows = [row(title="Logan"), row(title="X2"), row(title="X2"),
            row(type="ENEMY_OF", source_name="plot", evidence="they fight"),
            row(type="ALLY_OF", source_name="plot", evidence="they team up")]
    made = links(rows)
    assert [(l["label"], l["plot"], l["evidence"]) for l in made] == [
        ("plays", False, ["cast of Logan", "cast of X2"]),
        ("enemy of · ally of", True, ['enemy of: Logan: "they fight"', 'ally of: Logan: "they team up"'])]


def test_a_card_from_the_answer_with_no_link_is_left_out_but_the_questions_cards_stay():
    cards = [{"id": "q"}, {"id": "a1"}, {"id": "a2"}]
    found = [{"source": "q", "target": "a1"}]
    assert linked(cards, found, keep={"q"}) == [{"id": "q"}, {"id": "a1"}]
    assert linked([{"id": "q"}], [], keep={"q"}) == [{"id": "q"}]
