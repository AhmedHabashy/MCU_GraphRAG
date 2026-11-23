"""Unit tests for src/retrieval/evaluate.py (a fake judge; no network, no database)."""

import json

import pytest

from src.retrieval.evaluate import (
    CALIBRATION, MAX_RETRIEVED_CHARS, calibration_failures, cites_a_title, diagnose, judge, parse_questions,
    retrieved_text, summary,
)

TABLE = """Intro text.

| ID | Type | Question | Expected answer | Source |
| --- | --- | --- | --- | --- |
| Q01 | Multi-hop | Who plays Wanda? | Elizabeth Olsen. | data |
| Q12 | Timeline | In what year is Captain Marvel set? | 1995. | data |

## Data gaps
| ID | Gap |
| --- | --- |
| Q99 | not a question row |
"""


def test_questions_are_the_rows_of_the_first_table():
    assert parse_questions(TABLE) == [
        {"id": "Q01", "type": "Multi-hop", "question": "Who plays Wanda?", "expected": "Elizabeth Olsen.", "source": "data"},
        {"id": "Q12", "type": "Timeline", "question": "In what year is Captain Marvel set?", "expected": "1995.",
         "source": "data"}]


def test_the_real_evaluation_file_has_fifty_questions():
    from src.retrieval.evaluate import QUESTIONS_PATH
    questions = parse_questions(QUESTIONS_PATH.read_text(encoding="utf-8"))
    assert [q["id"] for q in questions] == [f"Q{i:02}" for i in range(1, 51)]


def test_retrieved_text_shows_each_call_and_its_result_and_is_capped():
    steps = [{"tool": "run_cypher", "arguments": {"query": "RETURN 1"}, "result": '{"rows": [1]}'}]
    text = retrieved_text(steps)
    assert "run_cypher" in text and "RETURN 1" in text and '{"rows": [1]}' in text
    big = [{"tool": "search_plots", "arguments": {"text": "x"}, "result": "y" * MAX_RETRIEVED_CHARS}] * 3
    assert len(retrieved_text(big)) <= MAX_RETRIEVED_CHARS + 100
    assert retrieved_text([]) == "(no tool was called)"


def fact(text, retrieved, answered, core=True):
    return {"fact": text, "retrieved": retrieved, "answered": answered, "core": core}


def verdict(*facts, contradictions=(), unsupported=()):
    return {"facts": list(facts), "contradictions": list(contradictions), "unsupported": list(unsupported)}


def test_the_grade_rests_on_the_core_facts_and_completeness_on_all_of_them():
    v = diagnose(verdict(fact("43", True, True), fact("born 1965", True, False, core=False)), "PASS")
    assert (v["grade"], v["cause"], v["complete"], v["supporting_left_out"]) == ("CORRECT", "OK", False, ["born 1965"])
    v = diagnose(verdict(fact("a", True, True), fact("b", True, True, core=False)), "PASS")
    assert v["complete"] and v["grade"] == "CORRECT"


def test_a_retrieved_core_fact_left_out_or_contradicted_is_a_generation_miss():
    v = diagnose(verdict(fact("a", True, True), fact("b", True, False)), "PASS")
    assert (v["grade"], v["cause"], v["dropped"]) == ("PARTIAL", "GENERATION", ["b"])
    v = diagnose(verdict(fact("a", True, True), contradictions=["says 2.05 billion"]), "PASS")
    assert (v["grade"], v["cause"]) == ("PARTIAL", "GENERATION")


def test_a_core_fact_not_retrieved_is_the_agents_query_when_the_graph_has_it_else_the_data():
    facts = (fact("a", True, True), fact("b", False, False))
    assert diagnose(verdict(*facts), "PASS")["cause"] == "QUERY"
    assert diagnose(verdict(*facts), "FACTS FOUND")["cause"] == "QUERY"
    assert diagnose(verdict(*facts), "PARTIAL")["cause"] == "QUERY/DATA"
    assert diagnose(verdict(*facts), "FAIL")["cause"] == "DATA"
    assert diagnose(verdict(*facts), None)["cause"] == "RETRIEVAL"
    both = diagnose(verdict(fact("a", False, False), fact("b", True, False)), "PASS")
    assert (both["grade"], both["cause"], both["not_retrieved"]) == ("WRONG", "QUERY+GENERATION", ["a"])


def test_a_fact_answered_from_the_models_own_knowledge_counts_as_not_retrieved():
    v = diagnose(verdict(fact("a", False, True), unsupported=["a"]), "PASS")
    assert (v["grade"], v["cause"], v["retrieval_recall"], v["unsupported"]) == ("CORRECT", "QUERY", 0.0, ["a"])


def test_without_core_facts_every_fact_counts_as_core():
    v = diagnose(verdict(fact("a", True, False, core=False)), "PASS")
    assert (v["grade"], v["cause"]) == ("WRONG", "GENERATION")


class FakeJudge:
    def __init__(self, verdict):
        self.verdict, self.requests = verdict, []

    def chat(self, messages, tools=None, **options):
        self.requests.append({"messages": messages, **options})
        return {"choices": [{"message": {"content": json.dumps(self.verdict)}}], "usage": {"cost": 0.0001}}


def test_judge_sends_question_expected_retrieved_and_answer_and_asks_for_the_schema():
    fake = FakeJudge(verdict(fact("Nebula", True, False)))
    v = judge(fake, "Who is in both teams?", "Thor, Nebula and Rocket.", '{"rows": ["Nebula"]}', "Thor.", "PASS")
    assert v["grade"] == "WRONG" and v["dropped"] == ["Nebula"] and v["cost"] == 0.0001
    prompt = fake.requests[0]["messages"][-1]["content"]
    assert all(x in prompt for x in ("Thor, Nebula and Rocket.", '{"rows": ["Nebula"]}', "Thor."))
    assert fake.requests[0]["response_format"]["type"] == "json_schema"


def test_a_verdict_without_facts_is_an_error():
    with pytest.raises(ValueError):
        judge(FakeJudge(verdict()), "q", "e", "r", "a", "PASS")


def test_calibration_covers_each_grade_and_cause_and_reports_what_the_judge_got_wrong():
    assert {c["grade"] for c in CALIBRATION} == {"CORRECT", "PARTIAL", "WRONG"}
    assert {"GENERATION", "RETRIEVAL"} <= {part for c in CALIBRATION for part in c["cause"].split("+")}
    assert any(c.get("supporting_left_out") for c in CALIBRATION)
    always_ok = FakeJudge(verdict(fact("a", True, True)))
    failures = calibration_failures(always_ok)
    assert len(failures) == len([c for c in CALIBRATION if (c["grade"], c["cause"]) != ("CORRECT", "OK")
                                 or c.get("unsupported") or c.get("supporting_left_out")])


def test_an_answer_cites_a_title_when_it_names_one():
    titles = ["Avengers: Endgame", "Loki, season 1"]
    assert cites_a_title("Sources: Avengers: Endgame", titles)
    assert cites_a_title("Sources: *Loki*, Season 1", titles)        # markdown and case are ignored
    assert not cites_a_title("I could not find an answer in the graph.", titles)


def test_summary_counts_grades_misses_by_kind_recall_citations_and_cost():
    results = [{"grade": "CORRECT", "complete": True, "cause": "OK", "retrieval_recall": 1.0, "unsupported": [],
                "cites": True, "cost": 0.002, "rounds": 3},
               {"grade": "PARTIAL", "complete": False, "cause": "QUERY+GENERATION", "retrieval_recall": 0.5,
                "unsupported": ["x"], "cites": False, "cost": 0.001, "rounds": 8}]
    assert summary(results) == {
        "questions": 2, "CORRECT": 1, "PARTIAL": 1, "WRONG": 0, "complete answers": 1, "no miss": 1,
        "misses QUERY": 1, "misses QUERY/DATA": 0, "misses DATA": 0, "misses RETRIEVAL": 0, "misses GENERATION": 1,
        "core retrieval recall": 0.75, "answers with unsupported claims": 1, "cite a title": 1,
        "cost": 0.003, "average rounds": 5.5}
