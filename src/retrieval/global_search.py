"""Global search (docs/rag_design.md, "Global search"): the written summaries that fit a question,
for big-picture questions. No LLM: the only model call is the question's embedding, made by the
caller.

1. The summaries of what the question names: a title, a main character, a team, or a group
   (series, phase, universe, saga, reality), matched as in local search.
2. The summaries found by the keyword and the vector index, the two rankings fused.
Each summary comes with its key facts and their citations; a group's also lists its titles. The
context is cut to MAX_CONTEXT_CHARS, each summary to a fair share (src.retrieval.local.fit).
"""

from src.retrieval.local import GraphReader, fit, group_title_line

MAX_SUMMARIES = 10
SUMMARY_IDS = {"Title": "title:{}", "Character": "character:{}", "Team": "team:{}", "Group": "{}"}
SUMMARIES = """UNWIND $ids AS id MATCH (s:Summary {id: id})
RETURN s.id AS id, s.kind AS kind, s.name AS name, s.level AS level, s.text AS text,
       s.key_facts AS facts, s.key_fact_cites AS cites,
       CASE WHEN s.level > 1 THEN COLLECT { MATCH (s)-[:SUMMARIZES]->(t:Title) RETURN t {.*} AS t
                                            ORDER BY t.release_order } ELSE [] END AS titles"""


def summary_ids(named, searched, limit=MAX_SUMMARIES):
    """The summary ids to show: those of the named entries first, then the searched ones, once each."""
    ids = [SUMMARY_IDS[c["kind"]].format(c["key"]) for c in named if c["kind"] in SUMMARY_IDS]
    return list(dict.fromkeys(ids + searched))[:limit]


def summary_block(row):
    """A summary with its key facts (and, for a group, its titles); the titles come last, so they
    are the part cut first."""
    lines = [f"## Summary ({row['kind']}): {row['name']}", row["text"]]
    if row["facts"]:
        lines += ["Key facts:"] + [f"- {f} {c}" for f, c in zip(row["facts"], row["cites"])]
    if row["titles"]:
        lines += [f"Titles ({len(row['titles'])}, in release order):"] + [f"- {group_title_line(t)}" for t in row["titles"]]
    return "\n".join(lines)


class GlobalSearch(GraphReader):
    """A strategy for src.retrieval.evaluation: (question, question vector) -> context text."""

    def __call__(self, question, vector):
        ids = summary_ids(self.named(question), self.searched("summaries", question, vector))
        rows = {r["id"]: r for r in self._read(SUMMARIES, ids=ids)}
        return fit([summary_block(rows[i]) for i in ids if i in rows], [])
