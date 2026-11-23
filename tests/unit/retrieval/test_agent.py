"""Unit tests for src/retrieval/agent.py (a fake model and fake tools; no network, no database)."""

import json

from src.retrieval.agent import Agent, Chat
from src.retrieval.tools import SCHEMAS


def reply(content=None, calls=(), usage=None):
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [{"id": f"call{i}", "type": "function",
                                  "function": {"name": name, "arguments": json.dumps(args)}}
                                 for i, (name, args) in enumerate(calls)]
    return {"choices": [{"message": message}],
            "usage": usage or {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.001,
                               "prompt_tokens_details": {"cached_tokens": 4}}}


class FakeModel:
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    def chat(self, messages, tools=None, **options):
        self.requests.append({"messages": [dict(m) for m in messages], "tools": tools, **options})
        return self.replies.pop(0)


class FakeTools:
    def __init__(self):
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, json.loads(arguments)))
        return json.dumps({"rows": [{"name": "Sharon Carter"}]})


def make_agent(*replies, max_rounds=8):
    model, tools = FakeModel(*replies), FakeTools()
    return Agent(model, tools, system_prompt="SYSTEM", max_rounds=max_rounds), model, tools


def ask(text):
    return [{"role": "user", "content": text}]


def test_a_direct_answer_takes_one_round_with_the_system_prompt_and_tools():
    agent, model, _ = make_agent(reply("Jon Favreau."))
    result = agent.answer(ask("Who directed Iron Man?"))
    assert result["answer"] == "Jon Favreau." and result["rounds"] == 1 and result["steps"] == []
    sent = model.requests[0]
    assert sent["messages"][0] == {"role": "system", "content": "SYSTEM"} and sent["tools"] == SCHEMAS


def test_tool_calls_run_and_their_results_go_back_to_the_model():
    agent, model, tools = make_agent(
        reply(calls=[("find_entity", {"name": "Batroc"}), ("search_plots", {"text": "Batroc dies"})]),
        reply("Sharon Carter (the Power Broker) kills him."))
    result = agent.answer(ask("Who killed Batroc?"))
    assert tools.calls == [("find_entity", {"name": "Batroc"}), ("search_plots", {"text": "Batroc dies"})]
    second = model.requests[1]["messages"]
    assert second[2]["tool_calls"] and [m["tool_call_id"] for m in second[3:]] == ["call0", "call1"]
    assert result["rounds"] == 2 and [s["tool"] for s in result["steps"]] == ["find_entity", "search_plots"]
    assert result["steps"][0]["arguments"] == {"name": "Batroc"} and "Sharon" in result["steps"][0]["result"]


def test_the_last_round_offers_no_tools_so_the_model_must_answer():
    agent, model, _ = make_agent(reply(calls=[("run_cypher", {"query": "RETURN 1"})]),
                                 reply(calls=[("run_cypher", {"query": "RETURN 2"})]),
                                 reply("Best answer so far."), max_rounds=3)
    result = agent.answer(ask("Hard question"))
    assert [r.get("tool_choice") for r in model.requests] == [None, None, "none"]
    assert result["answer"] == "Best answer so far." and result["rounds"] == 3


def test_a_model_that_never_answers_gets_a_plain_failure_message():
    agent, _, _ = make_agent(reply(calls=[("run_cypher", {"query": "RETURN 1"})]), reply(None), max_rounds=2)
    assert "could not" in agent.answer(ask("?"))["answer"]


def test_usage_is_summed_over_the_rounds():
    agent, _, _ = make_agent(reply(calls=[("find_entity", {"name": "x"})]), reply("done"))
    assert agent.answer(ask("?"))["usage"] == {"prompt_tokens": 20, "completion_tokens": 4, "cached_tokens": 8,
                                               "cost": 0.002}


def test_a_chat_remembers_questions_and_answers_but_not_tool_traffic():
    agent, model, _ = make_agent(reply(calls=[("find_entity", {"name": "Batroc"})]), reply("Sharon Carter."),
                                 reply("Emily VanCamp."))
    chat = Chat(agent)
    chat.ask("Who killed Batroc?")
    chat.ask("Who plays her?")
    sent = model.requests[2]["messages"]
    assert [(m["role"], m["content"]) for m in sent] == [
        ("system", "SYSTEM"), ("user", "Who killed Batroc?"), ("assistant", "Sharon Carter."),
        ("user", "Who plays her?")]


def test_a_chat_keeps_only_the_latest_turns():
    agent, model, _ = make_agent(reply("a1"), reply("a2"), reply("a3"))
    chat = Chat(agent, max_turns=1)
    for q in ("q1", "q2", "q3"):
        chat.ask(q)
    assert [m["content"] for m in model.requests[2]["messages"][1:]] == ["q2", "a2", "q3"]
