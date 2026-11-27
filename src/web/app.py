"""The front end for testing the RAG system (docs/rag_design.md, "The front end"): a Flask app that
serves the case board page and answers questions.

  GET  /          the page (src/web/static)
  POST /api/ask   {"question": ..., "strategy": "local" | "global" | "drift"} ->
                  {answer, cited, views, named, board: {cards, links}, retrieval_seconds, answer_seconds}

Errors name what went wrong, never the question or the keys. Run (Neo4j up, .env filled):
    .venv\\Scripts\\python.exe -m src.web.app            # http://127.0.0.1:5000
"""

import logging

from flask import Flask, jsonify, request

STRATEGY_NAMES = ("local", "global", "drift")
MAX_QUESTION_CHARS = 500
log = logging.getLogger(__name__)


def create_app(ask):
    """The app around ask: (question, strategy) -> the answer's JSON (see Asker)."""
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    @app.get("/")
    def page():
        return app.send_static_file("index.html")

    @app.post("/api/ask")
    def answer():
        body = request.get_json(silent=True) or {}
        question, strategy = str(body.get("question", "")).strip(), body.get("strategy", "local")
        if not question or len(question) > MAX_QUESTION_CHARS:
            return jsonify(error=f"Ask a question of 1 to {MAX_QUESTION_CHARS} characters."), 400
        if strategy not in STRATEGY_NAMES:
            return jsonify(error=f"The strategy is one of: {', '.join(STRATEGY_NAMES)}."), 400
        try:
            return jsonify(ask(question, strategy))
        except Exception as error:          # the page shows a message; the log keeps the error type only
            log.error("answering failed: %s", type(error).__name__)
            return jsonify(error="The answer failed; see the server log."), 502

    return app


class Asker:
    """(question, strategy) -> the answer with its cited lines and its case board."""

    def __init__(self, driver, client):
        from src.retrieval.aggregate import Views
        from src.retrieval.answer import Answerer
        from src.retrieval.board import Board
        from src.retrieval.evaluation import STRATEGIES
        views = Views(driver)
        self.strategies = {name: STRATEGIES[name](driver) for name in STRATEGY_NAMES}
        self.answerers = {name: Answerer(s, views, client.chat) for name, s in self.strategies.items()}
        self.board, self.client = Board(driver), client

    def __call__(self, question, strategy):
        # embedded directly, not through the query cache: the cache keeps only the evaluation questions
        vector = self.client.embed([question])[0]
        out = self.answerers[strategy](question, vector)
        named = [f"{c['names'][0]} ({c['kind'].lower()})" for c in self.strategies[strategy].named(question)]
        return {"question": question, "strategy": strategy, "answer": out["answer"], "cited": out["cited"],
                "views": out["views"], "named": named, "board": self.board(question, out["answer"]),
                "retrieval_seconds": out["retrieval_seconds"], "answer_seconds": out["answer_seconds"]}


def main():
    from src.graph.neo4j_db import connect
    from src.retrieval.openrouter import from_env
    logging.basicConfig(level=logging.INFO)
    with connect() as driver:
        create_app(Asker(driver, from_env())).run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
