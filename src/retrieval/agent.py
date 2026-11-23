"""The question-answering agent: the model calls the graph tools until it can answer.

Agent.answer(conversation) runs the tool loop for one turn: at most max_rounds requests, the last
one offering no tools, so the model answers with what it has found. The system prompt and the
tool list come first and never change, so the provider's prompt cache covers them.

Chat keeps the memory of a conversation: earlier questions and answers as text, not the tool
traffic (a follow-up sees who "her" is; the model looks IDs up again when it needs them), and
only the latest MEMORY_TURNS turns.

Run:  .venv\\Scripts\\python.exe -m src.retrieval.agent "Who killed Georges Batroc?"
      .venv\\Scripts\\python.exe -m src.retrieval.agent          (a chat; an empty line ends it)
"""

import json
import sys
from contextlib import contextmanager
from pathlib import Path

from src.graph.neo4j_db import connect
from src.retrieval.openrouter import from_env
from src.retrieval.tools import SCHEMAS, GraphTools

SYSTEM_PROMPT = (Path(__file__).with_name("system_prompt.md")).read_text(encoding="utf-8")
MAX_ROUNDS = 8
MEMORY_TURNS = 6           # question-answer pairs a chat remembers
SENT_BACK = ("role", "content", "tool_calls", "reasoning_details")   # of the model's own messages
NO_ANSWER = "I could not find an answer in the graph."


def add_usage(total, usage):
    total["prompt_tokens"] += usage.get("prompt_tokens", 0)
    total["completion_tokens"] += usage.get("completion_tokens", 0)
    total["cached_tokens"] += (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    total["cost"] = round(total["cost"] + usage.get("cost", 0), 8)


class Agent:
    def __init__(self, model, tools, system_prompt=SYSTEM_PROMPT, max_rounds=MAX_ROUNDS):
        self.model, self.tools, self.system_prompt, self.max_rounds = model, tools, system_prompt, max_rounds

    def answer(self, conversation):
        """{answer, steps (tool, arguments, full result), rounds, usage} for the conversation's last
        user message."""
        messages = [{"role": "system", "content": self.system_prompt}, *conversation]
        steps, usage = [], {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "cost": 0}
        for round_number in range(1, self.max_rounds + 1):
            last = round_number == self.max_rounds
            response = self.model.chat(messages, SCHEMAS, **({"tool_choice": "none"} if last else {}))
            add_usage(usage, response.get("usage") or {})
            message = response["choices"][0]["message"]
            calls = [] if last else message.get("tool_calls") or []
            if not calls:
                return {"answer": (message.get("content") or "").strip() or NO_ANSWER, "steps": steps,
                        "rounds": round_number, "usage": usage}
            messages.append({k: message[k] for k in SENT_BACK if message.get(k) is not None})
            for call in calls:
                name, arguments = call["function"]["name"], call["function"]["arguments"]
                result = self.tools.call(name, arguments)
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                steps.append({"tool": name, "arguments": _arguments(arguments), "result": result})
        return {"answer": NO_ANSWER, "steps": steps, "rounds": self.max_rounds, "usage": usage}


def _arguments(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


class Chat:
    def __init__(self, agent, max_turns=MEMORY_TURNS):
        self.agent, self.max_turns, self.history = agent, max_turns, []

    def ask(self, question):
        turn = {"role": "user", "content": question}
        result = self.agent.answer(self.history + [turn])
        self.history = (self.history + [turn, {"role": "assistant", "content": result["answer"]}])[-2 * self.max_turns:]
        return result


@contextmanager
def open_agent():
    """An Agent on the configured model and the running graph."""
    client = from_env()
    with connect() as driver:
        yield Agent(client, GraphTools(driver, client))


def show(result):
    print(result["answer"])
    trace = ", ".join(s["tool"] for s in result["steps"]) or "no tools"
    print(f"\n[{result['rounds']} rounds: {trace}; {result['usage']['prompt_tokens']} tokens in "
          f"({result['usage']['cached_tokens']} cached), {result['usage']['completion_tokens']} out, "
          f"${result['usage']['cost']:.4f}]")


def main():
    with open_agent() as agent:
        if len(sys.argv) > 1:
            show(agent.answer([{"role": "user", "content": " ".join(sys.argv[1:])}]))
            return
        chat = Chat(agent)
        while question := input("\nYou: ").strip():
            show(chat.ask(question))


if __name__ == "__main__":
    main()
