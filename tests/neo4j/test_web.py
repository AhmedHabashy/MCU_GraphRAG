"""The web app end to end on the loaded graph: real retrieval, board and aggregation views, a fake
model (no network). The question vectors come from the evaluation's query cache.

Run with:  .venv\\Scripts\\python.exe -m pytest -m neo4j
"""

import pytest

from src.graph.neo4j_db import connect
from src.retrieval.embeddings import EMBEDDINGS_DIR, text_key
from src.source_data_collection.storage import read_json
from src.web.app import STRATEGY_NAMES, Asker, create_app
from tests.neo4j.test_graph import count, db  # noqa: F401  (the db fixture)

pytestmark = pytest.mark.neo4j
CARTER = "Is Captain Carter the same character as Peggy Carter?"     # Q21
DIRECTORS = "Who directed the most films?"                            # Q08


class FakeClient:
    """Embeds from the query cache; answers with canned replies, calling a view when told to."""

    def __init__(self, replies=None):
        self.vectors = read_json(EMBEDDINGS_DIR / "queries.json")["vectors"]
        self.replies, self.sent = list(replies or []), []

    def embed(self, texts):
        return [self.vectors[text_key(t)] for t in texts]

    def chat(self, messages, tools=None, tool_choice=None):
        self.sent.append([dict(m) for m in messages])
        return self.replies.pop(0) if self.replies else {"role": "assistant", "content": "From the data [1, 2]."}


@pytest.fixture(scope="module")
def driver(db):  # noqa: F811
    if not count(db, "MATCH (s:Summary) RETURN count(s) AS n"):
        pytest.skip("summaries not loaded; run src.graph.load_summaries and src.retrieval.indexes")
    with connect() as d:
        yield d


def ask(driver, question, strategy, client):
    response = create_app(Asker(driver, client)).test_client().post(
        "/api/ask", json={"question": question, "strategy": strategy})
    assert response.status_code == 200, response.get_json()
    return response.get_json(), client


@pytest.mark.parametrize("strategy", STRATEGY_NAMES)
def test_every_strategy_answers_from_numbered_lines_and_returns_the_ones_it_cites(driver, strategy):
    data, client = ask(driver, CARTER, strategy, FakeClient())
    sent = client.sent[0][1]["content"]
    assert sent.startswith(f"Question: {CARTER}\n\nContext:\n") and "\n[1] " in sent
    assert [c["n"] for c in data["cited"]] == [1, 2]
    assert all(f"[{c['n']}] {c['text']}" in sent for c in data["cited"])
    assert data["retrieval_seconds"] < 2 and data["strategy"] == strategy


def test_the_board_shows_the_variants_the_question_names_with_their_shared_identity(driver):
    answer = {"role": "assistant", "content": "No. Captain Carter is a variant; Hayley Atwell plays her [1]."}
    data, _ = ask(driver, CARTER, "local", FakeClient([answer]))
    cards = {(c["label"], c["under"]) for c in data["board"]["cards"]}
    assert {("Captain Carter", "Earth-838"), ("Peggy Carter", "Earth-616"), ("Hayley Atwell", "")} <= cards
    labels = {l["label"] for l in data["board"]["links"]}
    assert {"variant of", "plays"} <= labels
    evidence = [e for l in data["board"]["links"] for e in l["evidence"]]
    assert any(e.startswith("Wikidata shared identity Q") for e in evidence)
    assert any(e.startswith("cast of Doctor Strange in the Multiverse of Madness") for e in evidence)
    ids = {c["id"] for c in data["board"]["cards"]}
    assert all(l["source"] in ids and l["target"] in ids for l in data["board"]["links"])


def test_a_count_goes_through_the_view_the_model_calls_and_its_lines_are_numbered_on(driver):
    call = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "aggregate", "arguments": '{"view": "directors"}'}}]}
    client = FakeClient([call, {"role": "assistant", "content": "The Russos [V]."}])
    data, _ = ask(driver, DIRECTORS, "local", client)
    view = client.sent[1][-1]["content"]
    first = int(view.split("\n")[1].split("]")[0].lstrip("["))
    assert view.startswith("## The 20 directors of the most films") and "Anthony Russo: 5 films" in view
    assert first > 1 and data["views"] == ["directors"]
    client = FakeClient([call, {"role": "assistant", "content": f"The Russos, five each [{first}]."}])
    data, _ = ask(driver, DIRECTORS, "local", client)
    assert data["cited"][0]["block"].startswith("The 20 directors") and "Russo" in data["cited"][0]["text"]


def test_a_question_that_names_nothing_still_answers_with_an_empty_board(driver):
    question = "How long after the snap is it reversed?"                   # Q15: names nothing
    data, _ = ask(driver, question, "local", FakeClient([{"role": "assistant", "content": "Five years."}]))
    assert data["named"] == [] and data["cited"] == []
    assert data["answer"] == "Five years."
