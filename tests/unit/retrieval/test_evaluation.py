"""Unit tests for src/retrieval/evaluation.py (temporary folders, no network, no database)."""

from src.retrieval.evaluation import QUESTIONS_PATH, judged, read_questions, report, run
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
    assert seen == [("When?", [1.0]), ("Who?", [2.0])]
    saved = read_json(tmp_path / "Q02.json")
    assert (saved["strategy"], saved["context"], saved["expected"]) == ("probe", "context for Who?", "Carol and Nick.")
    assert saved["seconds"] >= 0
    assert read_json(tmp_path / "batches.json") == [["C01", "Q02"]]


def test_the_report_counts_verdicts_lists_gaps_and_names_what_is_not_judged(tmp_path):
    run("probe", lambda q, v: "x" * 10, QUESTIONS, [[1.0], [2.0]], tmp_path)
    write_json(tmp_path / "Q02.judge.json", {"id": "Q02", "verdict": "partial", "conflicts": [], "items": [
        {"item": "Carol", "found": "yes"}, {"item": "Nick", "found": "no"}]})
    assert [j for _, j in judged(tmp_path)][0] is None
    text = report(tmp_path)
    assert "**Not judged yet:** C01" in text
    assert "complete 0 | partial 1 | missing 0 | of 2" in text
    assert "| Teams | 0 | 1 | 0 |" in text
    assert "| Q02 | partial |" in text and "Nick (no)" in text and "Carol" not in text.split("| Q02 |")[1]
