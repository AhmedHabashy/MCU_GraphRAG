"""Unit tests for src/retrieval/evaluation.py (temporary folders, no network, no database)."""

from src.retrieval.evaluation import QUESTIONS_PATH, answer_run, carry, combined, judged, read_questions, report, run
from src.source_data_collection.storage import read_json, write_json


def test_the_questions_table_gives_fifty_questions_with_every_field():
    questions = read_questions(QUESTIONS_PATH)
    assert [q["id"] for q in questions] == [f"Q{n:02d}" for n in range(1, 51)]
    assert all(q["type"] and q["question"] and q["expected"] and q["source"] for q in questions)
    assert questions[11]["question"] == "In what year is Captain Marvel set?" and questions[11]["expected"] == "1995."


QUESTIONS = [{"id": "C01", "type": "Timeline", "question": "When?", "expected": "1995.", "source": "data"},
             {"id": "Q02", "type": "Teams", "question": "Who?", "expected": "Carol and Nick.", "source": "data"}]


def test_a_run_saves_each_context_with_its_time_and_the_judges_batches(tmp_path):
    seen = []

    def retrieve(question, vector):
        seen.append((question, vector))
        return f"context for {question}"

    run("probe", retrieve, QUESTIONS, [[1.0], [2.0]], tmp_path)
    assert seen == [("When?", [1.0]), ("When?", [1.0]), ("Who?", [2.0])]       # an untimed warm-up first
    saved = read_json(tmp_path / "Q02.json")
    assert (saved["strategy"], saved["context"], saved["expected"]) == ("probe", "context for Who?", "Carol and Nick.")
    assert saved["seconds"] >= 0
    assert read_json(tmp_path / "batches.json") == [["C01", "Q02"]]


def judgement(verdict, *missing):
    return {"verdict": verdict, "conflicts": [], "items": [{"item": "Carol", "found": "yes"}]
            + [{"item": m, "found": "no"} for m in missing]}


def test_judgements_are_carried_over_only_for_the_same_context(tmp_path):
    before, after = tmp_path / "before", tmp_path / "after"
    run("probe", lambda q, v: "same", QUESTIONS, [[1.0], [2.0]], before)
    for qid in ("C01", "Q02"):
        for n in (1, 2):
            write_json(before / f"{qid}.judge{n}.json", judgement("complete"))
    run("probe", lambda q, v: "same" if q == "When?" else "changed", QUESTIONS, [[1.0], [2.0]], after)
    assert carry(after, before) == (1, 1)
    assert (after / "C01.judge1.json").exists() and not (after / "Q02.judge1.json").exists()
    assert read_json(after / "pending.json") == [["Q02"]]


def test_the_lower_verdict_counts_and_needs_every_judge():
    partial, complete = judgement("partial", "Nick"), judgement("complete")
    assert combined([complete, partial]) == ("partial", partial)
    assert combined([complete, complete]) == ("complete", complete)
    assert combined([complete, None]) == (None, None)
    assert combined([complete, {"verdict": "fine"}]) == (None, None)


def test_the_report_counts_lower_verdicts_lists_gaps_disagreements_and_what_is_not_judged(tmp_path):
    run("probe", lambda q, v: "x" * 10, QUESTIONS, [[1.0], [2.0]], tmp_path)
    write_json(tmp_path / "Q02.judge1.json", judgement("complete"))
    write_json(tmp_path / "Q02.judge2.json", judgement("partial", "Nick"))
    write_json(tmp_path / "C01.judge1.json", judgement("complete"))
    assert judged(tmp_path)[0][1][1] is None
    text = report(tmp_path)
    assert "**Not judged yet:** C01" in text
    assert "complete 0 | partial 1 | missing 0 | of 2 (the lower of 2 judges)" in text
    assert "| Teams | 0 | 1 | 0 |" in text
    assert "Judges disagree on 1: Q02 (complete / partial)" in text
    assert "| Q02 | partial |" in text and "Nick (no)" in text and "Carol" not in text.split("| Q02 |")[1]


class FakeAnswerer:
    """Answers from a fixed text; retrieve is what the warm-up calls."""

    def __init__(self, answer):
        self.answer, self.retrieved, self.asked = answer, [], []

    def retrieve(self, question, vector):
        self.retrieved.append(question)
        return "context"

    def __call__(self, question, vector):
        self.asked.append(question)
        return {"context": "context", "answer": self.answer(question), "views": ["directors"] if question == "Who?" else [],
                "retrieval_seconds": 0.1, "answer_seconds": 2.5}


def test_an_answer_run_warms_up_without_the_model_and_judges_the_answer(tmp_path):
    answerer = FakeAnswerer(lambda q: f"answer to {q}")
    answer_run("probe", answerer, QUESTIONS, [[1.0], [2.0]], tmp_path)
    assert answerer.retrieved == ["When?"] and answerer.asked == ["When?", "Who?"]
    saved = read_json(tmp_path / "Q02.json")
    assert (saved["answer"], saved["judged"], saved["seconds"], saved["answer_seconds"]) == ("answer to Who?", "answer", 0.1, 2.5)
    for qid in ("C01", "Q02"):
        for n in (1, 2):
            write_json(tmp_path / f"{qid}.judge{n}.json", judgement("complete"))
    text = report(tmp_path)
    assert text.startswith("# Answers: probe") and "Answer time per question: median 2.500 s" in text
    assert "Views called: Q02 (directors)" in text and "| Answer chars |" in text


def test_answer_judgements_are_carried_over_only_for_the_same_answer(tmp_path):
    before, after = tmp_path / "before", tmp_path / "after"
    answer_run("probe", FakeAnswerer(lambda q: "same"), QUESTIONS, [[1.0], [2.0]], before)
    for qid in ("C01", "Q02"):
        for n in (1, 2):
            write_json(before / f"{qid}.judge{n}.json", judgement("complete"))
    answer_run("probe", FakeAnswerer(lambda q: "same" if q == "When?" else "changed"), QUESTIONS, [[1.0], [2.0]], after)
    assert carry(after, before) == (1, 1)
    assert read_json(after / "pending.json") == [["Q02"]]
