"""DRIFT search (docs/rag_design.md, "DRIFT search"): start broad, then step down to the details.
No LLM: the only model call is the question's embedding, made by the caller; the steps follow the
summaries' PART_OF links, ranked by closeness to the question.

1. Primer: the group summaries (level 2 and 3) the question names or the summary search finds
   first, PRIMERS at most.
2. Down: from the primers, PART_OF steps to the summaries they were written from, keeping the
   CHILDREN closest to the question at each level (in all, not per parent), until the titles
   (level 1). The primers keep their title lists.
3. Details: for each title reached, its plot facts and plot passage closest to the question.
A question that names a title starts there. The context is cut to MAX_CONTEXT_CHARS, each part
to a fair share (src.retrieval.local.fit).
"""

from src.graph.summary_inputs import fact_line
from src.retrieval.global_search import SUMMARIES, summary_block
from src.retrieval.local import TITLE_FACTS, GraphReader, fit

PRIMERS = 2
CHILDREN = 3            # kept at each step down, in all (not per parent)
MAX_TITLES = 6
FACTS_PER_TITLE = 6
LEVELS = "MATCH (s:Summary) WHERE s.id IN $ids RETURN s.id AS id, s.level AS level"
CHILDREN_QUERY = """UNWIND $ids AS id MATCH (c:Summary)-[:PART_OF]->(:Summary {id: id})
WITH DISTINCT c ORDER BY vector.similarity.cosine(c.embedding, $v) DESC
RETURN c.id AS id, c.kind AS kind LIMIT $n"""
TITLE_OF = "MATCH (s:Summary)-[:SUMMARIZES]->(t:Title) WHERE s.id IN $ids AND s.kind IN ['title', 'season'] RETURN DISTINCT t.qid AS qid"
PASSAGE = """MATCH (p:Passage {title_qid: $qid}) WITH p ORDER BY vector.similarity.cosine(p.embedding, $v) DESC LIMIT 1
RETURN p.heading AS heading, p.text AS text"""


class DriftSearch(GraphReader):
    """A strategy for src.retrieval.evaluation: (question, question vector) -> context text."""

    def __call__(self, question, vector):
        named = [c for c in self.named(question) if c["kind"] in ("Title", "Group")]
        start = [f"title:{c['key']}" if c["kind"] == "Title" else c["key"] for c in named]
        searched = self.searched("summaries", question, vector)
        levels = {r["id"]: r["level"] for r in self._read(LEVELS, ids=list(dict.fromkeys(start + searched)))}
        primers = list(dict.fromkeys([i for i in start if i in levels]
                                     + [i for i in searched if levels.get(i, 0) > 1]))[:max(PRIMERS, len(start))]
        path, titles = list(primers), [i for i in primers if levels.get(i) == 1]
        frontier = [i for i in primers if levels.get(i, 0) > 1]
        while frontier and len(titles) < MAX_TITLES:
            children = [c for c in self._read(CHILDREN_QUERY, ids=frontier, v=vector, n=CHILDREN + len(path))
                        if c["id"] not in path][:CHILDREN]
            path += [c["id"] for c in children]
            titles += [c["id"] for c in children if c["kind"] in ("title", "season") and c["id"] not in titles]
            frontier = [c["id"] for c in children if c["kind"] not in ("title", "season", "character", "team")]
        rows = {r["id"]: r for r in self._read(SUMMARIES, ids=path)}
        # the primers keep their title lists (which titles a phase or saga has); the steps down don't
        blocks = [summary_block(rows[i] if i in primers else dict(rows[i], titles=[])) for i in path if i in rows]
        return fit(blocks + self._details(titles[:MAX_TITLES], vector), [])

    def _details(self, summary_ids, vector):
        """Per title reached: its closest plot facts and plot passage."""
        blocks = []
        for qid in (r["qid"] for r in self._read(TITLE_OF, ids=summary_ids)):
            facts = list(dict.fromkeys(fact_line(f) for f in self._read(TITLE_FACTS, key=qid, v=vector, n=FACTS_PER_TITLE)))
            passage = self._read(PASSAGE, qid=qid, v=vector)
            lines = [f"## Details: {passage[0]['heading'] if passage else qid}"]
            lines += ["Plot facts closest to the question:"] + [f"- {f}" for f in facts] if facts else []
            if passage:
                lines += ["Plot passage closest to the question:", passage[0]["text"]]
            blocks.append("\n".join(lines))
        return blocks
