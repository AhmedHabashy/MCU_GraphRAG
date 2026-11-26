"""The search indexes (docs/rag_design.md, "Index set"): plot passages, plot-fact evidence and
summaries each get a keyword (full-text) and a vector index; Character and Person get lookup
indexes for exact names. The name index is part of the graph build (src.graph.load_neo4j).

What is embedded (text-embedding-3-small, through src.retrieval.embeddings, so only new or changed
text is sent):
- a passage: its heading and text;
- a plot fact: its whole fact line, as the summary inputs show it ("[Q… ep N] Title: Subject
  RELATION Object: "evidence" (note: …)"), since many evidence sentences are fragments that
  don't say who acts or in which title;
- a summary: its name and text.
Passages are reloaded as (:Passage)-[:FROM]->(:Title); fact vectors go on the plot relationships,
summary vectors on the Summary nodes. Search indexes are dropped and created again on every run,
so they always match the definitions here.

Needs:  the loaded graph with its Summary nodes, OpenRouter settings in .env
Run after src.graph.load_neo4j, src.graph.profiles and src.graph.load_summaries:
    .venv\\Scripts\\python.exe -m src.retrieval.indexes
"""

from src.graph.check_extraction import RELATIONS
from src.graph.load_neo4j import run_batches
from src.graph.neo4j_db import connect
from src.graph.summary_inputs import fact_line, read_plots
from src.retrieval.embeddings import vectors_for
from src.retrieval.openrouter import from_env
from src.retrieval.passages import embedded_text, load_passages, plot_passages

PLOT_TYPES = "|".join(sorted(RELATIONS))     # MEMBER_OF from the wikis has no evidence, so it isn't indexed
FULLTEXT = {
    "passage_text": "FOR (n:Passage) ON EACH [n.heading, n.text]",
    "evidence_text": f"FOR ()-[n:{PLOT_TYPES}]-() ON EACH [n.evidence, n.note]",
    "summary_text": "FOR (n:Summary) ON EACH [n.name, n.text]",
}
VECTOR = {
    "passage_embedding": "FOR (n:Passage) ON n.embedding",
    "evidence_embedding": f"FOR ()-[n:{PLOT_TYPES}]-() ON n.embedding",
    "summary_embedding": "FOR (n:Summary) ON n.embedding",
}
LOOKUP = {
    "character_label": "FOR (n:Character) ON (n.label)",
    "character_reality": "FOR (n:Character) ON (n.reality)",
    "character_base_qid": "FOR (n:Character) ON (n.base_qid)",
    "person_name": "FOR (n:Person) ON (n.name)",
}
FACTS = """MATCH (a)-[r]->(b) WHERE r.source = 'plot'
           MATCH (t:Title {qid: r.title_qid})
           RETURN elementId(r) AS key, r.title_qid AS title_qid, t.title AS title, r.episode AS episode,
                  coalesce(a.label, a.name, a.title) AS subject, type(r) AS relation,
                  coalesce(b.label, b.name, b.title) AS object, r.evidence AS evidence, r.note AS note"""
SUMMARIES = "MATCH (s:Summary) RETURN s.id AS key, s.name AS name, s.text AS text ORDER BY key"
EMBEDDED = """MATCH (n:Passage) WHERE n.embedding IS NOT NULL RETURN 'passages' AS kind, count(n) AS n
              UNION ALL MATCH ()-[n]->() WHERE n.source = 'plot' AND n.embedding IS NOT NULL
                        RETURN 'evidence' AS kind, count(n) AS n
              UNION ALL MATCH (n:Summary) WHERE n.embedding IS NOT NULL RETURN 'summaries' AS kind, count(n) AS n"""
INDEX_WAIT_SECONDS = 600


def summary_text(summary):
    return f"{summary['name']}\n{summary['text']}"


def create_indexes(session, dimensions):
    """Drop and create every search index; create the lookup indexes if missing; wait until all
    are online. The names and definitions come from the tables above, not the data."""
    for name in (*FULLTEXT, *VECTOR):
        session.run(f"DROP INDEX {name} IF EXISTS")
    for name, definition in FULLTEXT.items():
        session.run(f"CREATE FULLTEXT INDEX {name} {definition}")
    for name, definition in VECTOR.items():
        session.run(f"CREATE VECTOR INDEX {name} {definition} OPTIONS {{indexConfig: "
                    f"{{`vector.dimensions`: {dimensions}, `vector.similarity_function`: 'cosine'}}}}")
    for name, definition in LOOKUP.items():
        session.run(f"CREATE INDEX {name} IF NOT EXISTS {definition}")
    session.run(f"CALL db.awaitIndexes({INDEX_WAIT_SECONDS})")


def main():
    embedder = from_env()
    passages = [p for plot in read_plots().values() for p in plot_passages(plot)]
    with connect() as driver, driver.session() as session:
        facts, summaries = session.run(FACTS).data(), session.run(SUMMARIES).data()
        if not summaries:
            raise RuntimeError("No Summary nodes: run src.graph.load_summaries first")
        texts = {"passages": [embedded_text(p) for p in passages], "evidence": [fact_line(f) for f in facts],
                 "summaries": [summary_text(s) for s in summaries]}
        vectors, embedded = {}, {}
        for kind, kind_texts in texts.items():
            vectors[kind], embedded[kind] = vectors_for(kind, kind_texts, embedder)
        load_passages(session, passages, vectors["passages"])
        run_batches(session, """UNWIND $rows AS r MATCH ()-[n]->() WHERE elementId(n) = r.key
                                SET n.embedding = r.embedding""",
                    [{"key": f["key"], "embedding": v} for f, v in zip(facts, vectors["evidence"])])
        run_batches(session, "UNWIND $rows AS r MATCH (n:Summary {id: r.key}) SET n.embedding = r.embedding",
                    [{"key": s["key"], "embedding": v} for s, v in zip(summaries, vectors["summaries"])])
        create_indexes(session, len(vectors["summaries"][0]))
        found = {r["kind"]: r["n"] for r in session.run(EMBEDDED)}
    expected = {kind: len(kind_texts) for kind, kind_texts in texts.items()}
    if found != expected:
        raise RuntimeError(f"Vectors in the graph {found}, expected {expected}")
    for kind, n in expected.items():
        print(f"{kind:10} {n:5} vectors ({embedded[kind]} embedded now, {n - embedded[kind]} from the cache)")
    print(f"{len(FULLTEXT)} full-text, {len(VECTOR)} vector and {len(LOOKUP)} lookup indexes online")


if __name__ == "__main__":
    main()
