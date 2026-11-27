"""Unit tests for src/retrieval/openrouter.py (fake session, no network)."""

import pytest

from src.retrieval.openrouter import OPENROUTER_API, OpenRouterClient, from_env
from tests.unit.test_utils import FakeResponse, FakeSession


def make_client(*payloads):
    session = FakeSession([FakeResponse(200, payload=p) for p in payloads])
    return OpenRouterClient("sk-or-SECRET", "embed/model", session=session, sleep=lambda _s: None), session


def test_the_key_goes_in_the_authorization_header_only():
    client, session = make_client({"data": [{"index": 0, "embedding": [1.0]}]})
    client.embed(["a"])
    assert session.headers["Authorization"] == "Bearer sk-or-SECRET"
    assert "SECRET" not in repr(session.calls)


def test_embed_returns_vectors_in_input_order_in_batches():
    client, session = make_client({"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]},
                                  {"data": [{"index": 0, "embedding": [3.0]}]})
    assert client.embed(["a", "b", "c"], batch_size=2) == [[1.0], [2.0], [3.0]]
    assert [body["input"] for _, body in session.calls] == [["a", "b"], ["c"]]
    assert session.calls[0][0] == f"{OPENROUTER_API}/embeddings" and session.calls[0][1]["model"] == "embed/model"


def test_an_error_in_a_200_response_raises_with_its_message_but_not_the_key_or_the_texts():
    client, _ = make_client({"error": {"code": 400, "message": "embed/model is not a valid model ID"}})
    with pytest.raises(RuntimeError) as error:
        client.embed(["private text"])
    assert "not a valid model" in str(error.value)
    assert "SECRET" not in str(error.value) and "private text" not in str(error.value)


def test_an_http_error_names_only_the_url():
    session = FakeSession([FakeResponse(401, payload={})])
    client = OpenRouterClient("sk-or-SECRET", "embed/model", session=session, sleep=lambda _s: None)
    with pytest.raises(RuntimeError) as error:
        client.embed(["private text"])
    assert str(error.value) == f"{OPENROUTER_API}/embeddings returned HTTP 401"


def test_chat_sends_the_qa_model_at_temperature_zero_and_returns_the_reply_message():
    message = {"role": "assistant", "content": "1995."}
    session = FakeSession([FakeResponse(200, payload={"choices": [{"message": message}]})])
    client = OpenRouterClient("sk-or-SECRET", "embed/model", "qa/model", session=session, sleep=lambda _s: None)
    tools = [{"type": "function", "function": {"name": "aggregate"}}]
    assert client.chat([{"role": "user", "content": "When?"}], tools, "auto") == message
    url, body = session.calls[0]
    assert url == f"{OPENROUTER_API}/chat/completions"
    assert (body["model"], body["temperature"], body["tools"], body["tool_choice"]) == ("qa/model", 0, tools, "auto")


def test_a_chat_error_gives_the_message_but_not_the_key_or_the_messages():
    session = FakeSession([FakeResponse(200, payload={"error": {"code": 429, "message": "rate limited"}})])
    client = OpenRouterClient("sk-or-SECRET", "embed/model", "qa/model", session=session, sleep=lambda _s: None)
    with pytest.raises(RuntimeError) as error:
        client.chat([{"role": "user", "content": "private question"}])
    assert "rate limited" in str(error.value)
    assert "SECRET" not in str(error.value) and "private question" not in str(error.value)


def test_from_env_names_missing_settings_without_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=sk-or-SECRET\n")
    with pytest.raises(RuntimeError) as error:
        from_env(env)
    assert "EMBEDDING_MODEL, QA_MODEL" in str(error.value) and "SECRET" not in str(error.value)
    env.write_text("OPENROUTER_API_KEY=sk-or-SECRET\nEMBEDDING_MODEL=embed/model\nQA_MODEL=qa/model\n")
    client = from_env(env)
    assert (client.embedding_model, client.qa_model) == ("embed/model", "qa/model")
