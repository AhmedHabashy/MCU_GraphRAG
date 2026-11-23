"""Unit tests for src/retrieval/openrouter.py (fake session, no network)."""

import pytest

from src.retrieval.openrouter import OPENROUTER_API, OpenRouterClient, from_env
from tests.unit.test_utils import FakeResponse, FakeSession


def make_client(*payloads):
    session = FakeSession([FakeResponse(200, payload=p) for p in payloads])
    return OpenRouterClient("sk-or-SECRET", "chat/model", "embed/model", session=session, sleep=lambda _s: None), session


def test_the_key_goes_in_the_authorization_header_only():
    client, session = make_client({"choices": [{"message": {"role": "assistant", "content": "hi"}}]})
    client.chat([{"role": "user", "content": "hello"}])
    assert session.headers["Authorization"] == "Bearer sk-or-SECRET"
    assert "SECRET" not in repr(session.calls)


def test_chat_sends_the_model_messages_and_tools_and_returns_the_response():
    reply = {"choices": [{"message": {"role": "assistant", "content": "hi"}}], "usage": {"total_tokens": 3}}
    client, session = make_client(reply)
    tools = [{"type": "function", "function": {"name": "f", "parameters": {"type": "object"}}}]
    assert client.chat([{"role": "user", "content": "hello"}], tools) == reply
    url, body = session.calls[0]
    assert url == f"{OPENROUTER_API}/chat/completions"
    assert body["model"] == "chat/model" and body["tools"] == tools and body["messages"][0]["content"] == "hello"


def test_chat_without_tools_sends_no_tools_field_and_passes_options_through():
    client, session = make_client({"choices": [{"message": {"content": "hi"}}]})
    client.chat([{"role": "user", "content": "hello"}], response_format={"type": "json_object"})
    assert "tools" not in session.calls[0][1]
    assert session.calls[0][1]["response_format"] == {"type": "json_object"}


def test_embed_returns_vectors_in_input_order_in_batches():
    client, session = make_client({"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]},
                                  {"data": [{"index": 0, "embedding": [3.0]}]})
    assert client.embed(["a", "b", "c"], batch_size=2) == [[1.0], [2.0], [3.0]]
    assert [body["input"] for _, body in session.calls] == [["a", "b"], ["c"]]
    assert session.calls[0][0] == f"{OPENROUTER_API}/embeddings" and session.calls[0][1]["model"] == "embed/model"


def test_an_error_in_a_200_response_raises_with_its_message_but_not_the_key():
    client, _ = make_client({"error": {"code": 400, "message": "chat/model is not a valid model ID"}})
    with pytest.raises(RuntimeError) as error:
        client.chat([{"role": "user", "content": "hello"}])
    assert "not a valid model" in str(error.value) and "SECRET" not in str(error.value)


def test_from_env_names_missing_settings_without_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=sk-or-SECRET\nQA_MODEL=chat/model\n")
    with pytest.raises(RuntimeError) as error:
        from_env(env)
    assert "EMBEDDING_MODEL" in str(error.value) and "SECRET" not in str(error.value)
    env.write_text("OPENROUTER_API_KEY=sk-or-SECRET\nQA_MODEL=chat/model\nEMBEDDING_MODEL=embed/model\n")
    client = from_env(env)
    assert (client.chat_model, client.embedding_model) == ("chat/model", "embed/model")
