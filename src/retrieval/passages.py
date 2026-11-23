"""Plot passages for vector search: split the Wikipedia plots, embed what is new, load into Neo4j.

A film's plot is split into whole paragraphs grouped up to MAX_CHARS; a series gives passages per
episode (episodes sharing one summary, the parts of a multi-part episode, give one passage). Each
passage is embedded with its heading (title, episode), so a search can match on those too.

Vectors are cached by passage ID (a hash of the title, heading and text) with the model's name:
a rerun embeds only new or changed passages; changing EMBEDDING_MODEL embeds everything again.
Passages are then reloaded as (:Passage)-[:FROM]->(:Title) with a vector index and a full-text
index (src.retrieval.tools searches both and fuses the rankings). Run this after
src.graph.load_neo4j, which clears the database.

Needs:  source_data/wikipedia/plots/, the loaded graph, OpenRouter settings in .env
Output: processed_data/retrieval/embeddings.json (the vector cache), Passage nodes in Neo4j
Run:    .venv\\Scripts\\python.exe -m src.retrieval.passages
"""

import hashlib
import json

from src.graph.load_neo4j import run_batches
from src.graph.neo4j_db import connect
from src.retrieval.openrouter import from_env
from src.source_data_collection.storage import read_json
from src.source_data_collection.tier_titles import PROJECT_ROOT

PLOTS_DIR = PROJECT_ROOT / "source_data" / "wikipedia" / "plots"
CACHE_PATH = PROJECT_ROOT / "processed_data" / "retrieval" / "embeddings.json"
MAX_CHARS = 1500
INDEX = "passage_embedding"
TEXT_INDEX = "passage_text"      # keyword search: catches names (Vormir, Batroc) the vectors can miss


def group_paragraphs(text, max_chars=MAX_CHARS):
    """Whole paragraphs joined up to max_chars; a longer paragraph is a group of its own."""
    groups, current = [], []
    for paragraph in (p.strip() for p in text.split("\n")):
        if not paragraph:
            continue
        if current and len("\n\n".join(current + [paragraph])) > max_chars:
            groups.append("\n\n".join(current))
            current = []
        current.append(paragraph)
    return groups + (["\n\n".join(current)] if current else [])


def _episode_heading(title, episodes):
    first, last = episodes[0], episodes[-1]
    numbers = (f"episode {first['number_overall']}" if len(episodes) == 1
               else f"episodes {first['number_overall']}-{last['number_overall']}")
    return f"{title}, {numbers} (season {first['season']}): {first['title']}"


def _passage(title_qid, heading, episodes, text):
    digest = hashlib.sha1(f"{title_qid}\n{heading}\n{text}".encode("utf-8")).hexdigest()[:16]
    return {"id": digest, "title_qid": title_qid, "heading": heading, "episodes": episodes, "text": text}


def plot_passages(plot, max_chars=MAX_CHARS):
    """The passages of one plot file."""
    by_summary = {}
    for e in plot.get("episodes") or []:
        if e.get("summary_text"):
            by_summary.setdefault(e["summary_text"], []).append(e)
    if not by_summary:
        return [_passage(plot["title_qid"], plot["title"], [], text)
                for text in group_paragraphs(plot.get("text") or "", max_chars)]
    return [_passage(plot["title_qid"], _episode_heading(plot["title"], episodes),
                     [e["number_overall"] for e in episodes], text)
            for summary, episodes in by_summary.items() for text in group_paragraphs(summary, max_chars)]


def embedded_text(passage):
    return f"{passage['heading']}\n{passage['text']}"


def embed_new(passages, cache, embedder):
    """(cache with a vector for exactly these passages, how many were embedded now)."""
    vectors = cache["vectors"] if cache.get("model") == embedder.embedding_model else {}
    new = [p for p in passages if p["id"] not in vectors]
    if new:
        vectors.update(zip((p["id"] for p in new), embedder.embed([embedded_text(p) for p in new])))
    return {"model": embedder.embedding_model, "vectors": {p["id"]: vectors[p["id"]] for p in passages}}, len(new)


def load_passages(session, passages, vectors):
    session.run("MATCH (p:Passage) DETACH DELETE p")
    session.run("CREATE CONSTRAINT passage_id IF NOT EXISTS FOR (p:Passage) REQUIRE p.id IS UNIQUE")
    run_batches(session, """UNWIND $rows AS r MATCH (t:Title {qid: r.title_qid})
                            CREATE (p:Passage {id: r.id, title_qid: r.title_qid, heading: r.heading,
                                               episodes: r.episodes, text: r.text, embedding: r.embedding})
                            CREATE (p)-[:FROM]->(t)""",
                [dict(p, embedding=vectors[p["id"]]) for p in passages])
    session.run(f"DROP INDEX {INDEX} IF EXISTS")
    dimensions = len(next(iter(vectors.values())))
    session.run(f"CREATE VECTOR INDEX {INDEX} FOR (p:Passage) ON p.embedding OPTIONS {{indexConfig: "
                f"{{`vector.dimensions`: {dimensions}, `vector.similarity_function`: 'cosine'}}}}")
    session.run(f"CREATE FULLTEXT INDEX {TEXT_INDEX} IF NOT EXISTS FOR (p:Passage) ON EACH [p.heading, p.text]")
    session.run("CALL db.awaitIndexes(300)")


def main():
    passages = [p for path in sorted(PLOTS_DIR.glob("*.json")) for p in plot_passages(read_json(path))]
    cache = read_json(CACHE_PATH) if CACHE_PATH.exists() else {"model": None, "vectors": {}}
    cache, embedded = embed_new(passages, cache, from_env())
    if embedded:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")      # compact: ~1,500 floats per passage
    with connect() as driver, driver.session() as session:
        load_passages(session, passages, cache["vectors"])
    print(f"{len(passages)} passages ({embedded} embedded now, {len(passages) - embedded} from the cache)")


if __name__ == "__main__":
    main()
