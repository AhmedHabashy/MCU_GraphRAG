"""Plot passages: the Wikipedia plots split for search, loaded as (:Passage)-[:FROM]->(:Title).

A film's plot is split into whole paragraphs grouped up to MAX_CHARS; a series gives passages per
episode (episodes sharing one summary, the parts of a multi-part episode, give one passage). Each
passage is embedded with its heading (title, episode), so a search can match on those too.
Loaded and indexed by src.retrieval.indexes.
"""

import hashlib

from src.graph.load_neo4j import run_batches

MAX_CHARS = 1500


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


def load_passages(session, passages, vectors):
    """Replace every Passage with these, each with its vector and its FROM link."""
    session.run("CREATE CONSTRAINT passage_id IF NOT EXISTS FOR (p:Passage) REQUIRE p.id IS UNIQUE")
    session.run("MATCH (p:Passage) DETACH DELETE p")
    run_batches(session, """UNWIND $rows AS r MATCH (t:Title {qid: r.title_qid})
                            CREATE (p:Passage {id: r.id, title_qid: r.title_qid, heading: r.heading,
                                               episodes: r.episodes, text: r.text, embedding: r.embedding})
                            CREATE (p)-[:FROM]->(t)""",
                [dict(p, embedding=v) for p, v in zip(passages, vectors)])
