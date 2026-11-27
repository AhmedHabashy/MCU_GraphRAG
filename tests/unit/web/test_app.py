"""Unit tests for src/web/app.py (a fake asker, no database or network)."""

from src.web.app import create_app


def client(ask):
    return create_app(ask).test_client()


def test_the_page_is_served():
    response = client(lambda q, s: {}).get("/")
    assert response.status_code == 200 and b"Ask the Graph" in response.data


def test_a_question_goes_to_the_asker_with_its_strategy():
    seen = []
    response = client(lambda q, s: seen.append((q, s)) or {"answer": "1995 [1]."}).post(
        "/api/ask", json={"question": "  When is Captain Marvel set? ", "strategy": "global"})
    assert response.status_code == 200 and response.get_json() == {"answer": "1995 [1]."}
    assert seen == [("When is Captain Marvel set?", "global")]


def test_a_bad_request_is_refused_without_asking():
    c = client(lambda q, s: (_ for _ in ()).throw(AssertionError("not asked")))
    assert c.post("/api/ask", json={"question": ""}).status_code == 400
    assert c.post("/api/ask", json={"question": "x" * 501}).status_code == 400
    assert c.post("/api/ask", json={"question": "Who?", "strategy": "web"}).status_code == 400


def test_a_failure_gives_a_message_without_the_question_or_the_error_text():
    def fail(q, s):
        raise RuntimeError("https://openrouter.ai/api/v1 secret detail")
    response = client(fail).post("/api/ask", json={"question": "private question"})
    assert response.status_code == 502
    body = response.get_data(as_text=True)
    assert "private question" not in body and "secret" not in body
