"""The answer step (docs/rag_design.md, "The answer step"): the QA model answers a question from
the context of the strategy the user picked, and can call the aggregation tool for a view over
the whole graph (counts, rankings, averages) instead of counting from the context.

The rules are in answer_prompt.md. The model may call the tool in at most MAX_TOOL_ROUNDS
rounds; the round after that it must answer (tool_choice "none").
"""

import json
import time
from pathlib import Path

from src.retrieval.aggregate import VIEWS

PROMPT_PATH = Path(__file__).with_name("answer_prompt.md")
MAX_TOOL_ROUNDS = 2
TOOL_NAME = "aggregate"


def aggregate_tool():
    """The OpenAI-style function the model calls, listing every view with its description."""
    listing = "\n".join(f"- {name}: {view['description']}" for name, view in VIEWS.items())
    return {"type": "function", "function": {
        "name": TOOL_NAME,
        "description": "A view computed over the whole graph (every title, character or person), for counts, "
                       "rankings, 'the most', averages and complete lists. The views:\n" + listing,
        "parameters": {"type": "object", "required": ["view"], "properties": {
            "view": {"type": "string", "enum": list(VIEWS), "description": "The name of the view."}}}}}


def user_message(question, context):
    return f"Question: {question}\n\nContext:\n{context}"


def view_name(call):
    """The view a tool call asks for, or None when the call isn't a valid aggregate call."""
    function = call.get("function", {})
    try:
        name = json.loads(function.get("arguments") or "{}").get("view")
    except (json.JSONDecodeError, AttributeError):
        return None
    return name if function.get("name") == TOOL_NAME and name in VIEWS else None


class Answerer:
    """(question, question vector) -> {context, answer, views, retrieval_seconds, answer_seconds}.

    retrieve: a strategy, (question, vector) -> context text; views: has block(name) -> text
    (src.retrieval.aggregate.Views); chat: (messages, tools, tool_choice) -> reply message
    (src.retrieval.openrouter.OpenRouterClient.chat)."""

    def __init__(self, retrieve, views, chat, prompt=None):
        self.retrieve, self.views, self.chat = retrieve, views, chat
        self.prompt = prompt if prompt is not None else PROMPT_PATH.read_text(encoding="utf-8")
        self.tools = [aggregate_tool()]

    def __call__(self, question, vector):
        start = time.perf_counter()
        context = self.retrieve(question, vector)
        retrieved = time.perf_counter()
        answer, called = self.answer(question, context)
        return {"context": context, "answer": answer, "views": called,
                "retrieval_seconds": round(retrieved - start, 4),
                "answer_seconds": round(time.perf_counter() - retrieved, 4)}

    def answer(self, question, context):
        """(the answer text, the views called in order)."""
        messages = [{"role": "system", "content": self.prompt}, {"role": "user", "content": user_message(question, context)}]
        called = []
        for round_ in range(MAX_TOOL_ROUNDS + 1):
            last = round_ == MAX_TOOL_ROUNDS
            reply = self.chat(messages, self.tools, "none" if last else "auto")
            calls = reply.get("tool_calls") or []
            if not calls or last:
                if not (reply.get("content") or "").strip():
                    raise RuntimeError(f"the QA model gave no answer after {round_} tool rounds")
                return reply["content"].strip(), called
            messages.append({"role": "assistant", "content": reply.get("content"), "tool_calls": calls})
            for call in calls:
                name = view_name(call)
                called.append(name or "unknown")
                content = (self.views.block(name) if name else
                           f"Unknown view. Call {TOOL_NAME} with one of: {', '.join(VIEWS)}.")
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": content})
