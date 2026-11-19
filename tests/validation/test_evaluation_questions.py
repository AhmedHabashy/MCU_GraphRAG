"""Validation of the evaluation question set (docs/evaluation_questions.md).

Run:  .venv\\Scripts\\python.exe -m pytest -m validation
"""

from collections import Counter

import pytest

from src.source_data_collection.tier_titles import PROJECT_ROOT, read_table

pytestmark = pytest.mark.validation

QUESTIONS_PATH = PROJECT_ROOT / "docs" / "evaluation_questions.md"
QUESTION_COUNT = 50
# The plan's question types, without comics (out of scope for now)
TYPES = {"Multi-hop", "Timeline", "Identity", "Teams", "Big picture", "Analytics"}
MIN_PER_TYPE = 5
SOURCES = {"data", "plot text", "expert"}


@pytest.fixture(scope="module")
def questions():
    return read_table(QUESTIONS_PATH, "# Evaluation questions")


def test_there_are_fifty_questions_with_unique_ids(questions):
    assert [q["id"] for q in questions] == [f"Q{n:02d}" for n in range(1, QUESTION_COUNT + 1)]


def test_every_question_type_is_covered(questions):
    counts = Counter(q["type"] for q in questions)
    assert set(counts) == TYPES
    assert {t: n for t, n in counts.items() if n < MIN_PER_TYPE} == {}


def test_every_question_has_an_answer_and_a_known_source(questions):
    """A '|' inside an answer would shift the cells, so the source check also catches it."""
    assert [q["id"] for q in questions
            if not (q["question"].endswith("?") and q["expected answer"] and q["source"] in SOURCES)] == []


def test_questions_are_not_repeated(questions):
    texts = Counter(q["question"].lower() for q in questions)
    assert [t for t, n in texts.items() if n > 1] == []
