"""Unit tests for src/retrieval/answer.py (a fake model and fake views, no network or database)."""

import json

import pytest

from src.retrieval.aggregate import VIEWS
from src.retrieval.answer import (
    MAX_TOOL_ROUNDS, Answerer, Lines, aggregate_tool, cited_numbers, view_name, without_citations,
)


def call(view, cid="c1", name="aggregate"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps({"view": view})}}


class FakeChat:
    """Returns queued reply messages and records what it was sent."""

    def __init__(self, *replies):
        self.replies, self.sent = list(replies), []

    def __call__(self, messages, tools, tool_choice):
        self.sent.append(([dict(m) for m in messages], tools, tool_choice))
        return self.replies.pop(0)


class FakeViews:
    def block(self, name):
        return f"## view {name}"


def answerer(chat):
    return Answerer(lambda q, v: f"context for {q}", FakeViews(), chat, prompt="RULES")


def test_the_tool_lists_every_view_by_name():
    tool = aggregate_tool()["function"]
    assert tool["parameters"]["properties"]["view"]["enum"] == list(VIEWS)
    assert all(f"- {name}: " in tool["description"] for name in VIEWS)


def test_an_answer_without_a_tool_call_comes_from_the_rules_the_question_and_the_context():
    chat = FakeChat({"role": "assistant", "content": " 1995. "})
    out = answerer(chat)("When is Captain Marvel set?", [1.0])
    assert (out["context"], out["answer"], out["views"]) == ("context for When is Captain Marvel set?", "1995.", [])
    assert out["retrieval_seconds"] >= 0 and out["answer_seconds"] >= 0
    messages, tools, choice = chat.sent[0]
    assert messages[0] == {"role": "system", "content": "RULES"}
    assert messages[1]["content"] == "Question: When is Captain Marvel set?\n\nContext:\n[1] context for When is Captain Marvel set?"
    assert tools[0]["function"]["name"] == "aggregate" and choice == "auto"


def test_a_view_call_is_answered_with_the_view_and_the_model_answers_from_it():
    chat = FakeChat({"role": "assistant", "content": None, "tool_calls": [call("directors")]},
                    {"role": "assistant", "content": "The Russos, five films each."})
    out = answerer(chat)("Who directed the most films?", [1.0])
    assert out["answer"] == "The Russos, five films each." and out["views"] == ["directors"]
    messages = chat.sent[1][0]
    assert messages[2]["tool_calls"] == [call("directors")]
    assert messages[3] == {"role": "tool", "tool_call_id": "c1", "content": "## view directors"}


def test_an_unknown_view_is_told_the_valid_names_instead_of_failing():
    assert view_name(call("box office")) is None and view_name(call("budget", name="other")) is None
    assert view_name({"function": {"name": "aggregate", "arguments": "not json"}}) is None
    chat = FakeChat({"role": "assistant", "content": "", "tool_calls": [call("box office")]},
                    {"role": "assistant", "content": "Endgame."})
    out = answerer(chat)("Which title grossed the most?", [1.0])
    assert out["views"] == ["unknown"]
    assert chat.sent[1][0][3]["content"].startswith("Unknown view. Call aggregate with one of: box_office, budget")


def test_after_the_last_tool_round_the_model_must_answer():
    calls = [{"role": "assistant", "content": "", "tool_calls": [call("ratings", f"c{n}")]} for n in range(MAX_TOOL_ROUNDS)]
    chat = FakeChat(*calls, {"role": "assistant", "content": "Avengers: Endgame."})
    out = answerer(chat)("Which is rated highest?", [1.0])
    assert out["answer"] == "Avengers: Endgame." and out["views"] == ["ratings"] * MAX_TOOL_ROUNDS
    assert [choice for _, _, choice in chat.sent] == ["auto"] * MAX_TOOL_ROUNDS + ["none"]


def test_no_answer_text_raises():
    with pytest.raises(RuntimeError, match="no answer"):
        answerer(FakeChat({"role": "assistant", "content": "  "}))("Who?", [1.0])


def test_lines_are_numbered_across_texts_without_headings_or_cut_marks_and_cited_ones_come_back():
    lines = Lines()
    assert lines.number("## Title: Logan\nLogan dies.\n\n[cut]") == "## Title: Logan\n[1] Logan dies.\n\n[cut]"
    assert lines.number("## Directors\n- Russo: 5") == "## Directors\n[2] - Russo: 5"
    assert lines.cited("Logan dies [1]. The Russos lead [2, 1]; see [9].") == [
        {"n": 1, "block": "Title: Logan", "text": "Logan dies."}, {"n": 2, "block": "Directors", "text": "- Russo: 5"}]


def test_the_answer_comes_back_with_the_lines_it_cites():
    chat = FakeChat({"role": "assistant", "content": "It is set in 1995 [1]."})
    assert answerer(chat)("When?", [1.0])["cited"] == [{"n": 1, "block": "", "text": "context for When?"}]


def test_citations_may_be_ranges_and_come_out_before_names_are_read():
    assert cited_numbers("Yes [1–3, 6] and [24-25].") == {1, 2, 3, 6, 24, 25}
    assert without_citations("X-24 is a clone [24–29].") == "X-24 is a clone ."
