"""Unit tests for src/graph/check_extraction.py."""

from src.graph.check_extraction import fact_problems

SOURCE = {"title_qid": "Q1", "cast": [{"id": "Q10@Earth-616"}], "teams": ["Avengers@Earth-616"],
          "text": "Wade joins the Avengers. Logan fights Wade."}


def fact(**overrides):
    base = {"subject_id": "Q10@Earth-616", "subject_name": "Wade", "relation": "MEMBER_OF",
            "object_id": "Avengers@Earth-616", "object_name": "Avengers", "object_type": "team",
            "episode": None, "evidence": "Wade joins the Avengers.", "note": ""}
    return {**base, **overrides}


def problems(*facts):
    return [p for _, p in fact_problems(SOURCE, {"title_qid": "Q1", "facts": list(facts)})]


def test_a_correct_fact_has_no_problems():
    assert problems(fact()) == []


def test_invented_ids_and_misquoted_evidence_are_caught():
    assert problems(fact(object_id="Q99@Earth-616")) == ["object_id Q99@Earth-616 is not in the cast or teams"]
    assert problems(fact(evidence="Wade joined the Avengers.")) == ["evidence is not an exact quote of the text"]


def test_unknown_relations_and_duplicates_are_caught():
    assert problems(fact(relation="LIKES")) == ["unknown relation LIKES"]
    assert problems(fact(), fact()) == ["duplicate fact"]


def test_unlinked_names_are_allowed():
    assert problems(fact(subject_id="", subject_name="Logan", relation="ENEMY_OF", object_type="character",
                         evidence="Logan fights Wade.")) == []
