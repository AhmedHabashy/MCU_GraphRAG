"""The tools the answering model calls: find_entity, run_cypher and search_plots.

find_entity   names to node IDs, through the full-text index over names and aliases
              (load_neo4j.NAME_INDEX); with a few titles each, to tell same-named variants apart
run_cypher    a read-only Cypher query. EXPLAIN must report a read query ('r'), and the query
              then runs in a read transaction with a timeout. Rows are capped by count and size.
search_plots  plot passages for a description: the vector and full-text rankings fused by
              reciprocal rank (keywords catch names, vectors catch paraphrases)

Every tool returns a JSON-able dict. A bad call (unknown tool, bad arguments, a Cypher error)
comes back as {"error": ...} for the model to fix, instead of raising.
"""

import json
import re

from neo4j import READ_ACCESS, unit_of_work
from neo4j.exceptions import Neo4jError
from neo4j.graph import Node, Path, Relationship

from src.graph.load_neo4j import NAME_INDEX
from src.retrieval.passages import INDEX as VECTOR_INDEX
from src.retrieval.passages import TEXT_INDEX

ROW_LIMIT = 200
MAX_RESULT_CHARS = 20_000       # what one tool result may add to the model's context
CYPHER_TIMEOUT = 15             # seconds
ENTITY_LIMIT = 10
PASSAGE_LIMIT = 8
CANDIDATES = 50                 # per ranking, before fusing
RRF_K = 60                      # the usual reciprocal-rank-fusion constant
HIDDEN = {"embedding"}          # properties never shown to the model

SCHEMAS = [
    {"type": "function", "function": {
        "name": "find_entity",
        "description": "Find titles, characters, people, teams and things by name or alias. Returns each "
                       "match's label, id (use it in Cypher), reality and how many titles it is in. Call this "
                       "before writing Cypher about a named entity: a name can have several variants.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "run_cypher",
        "description": f"Run one read-only Cypher query on the graph (schema in the system prompt). At most "
                       f"{ROW_LIMIT} rows are returned; aggregate or LIMIT large results. Write queries are rejected.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "search_plots",
        "description": f"Search the Wikipedia plot summaries for events described in words. Returns the top "
                       f"{PASSAGE_LIMIT} passages with their title and episodes. Use it for what happens in a "
                       f"story, and to check facts the graph lacks.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
]
TOOLS = {s["function"]["name"]: s["function"]["parameters"] for s in SCHEMAS}


def lucene_text(text):
    """Plain words for a full-text query: no Lucene syntax, operators lowercased into words."""
    words = re.sub(r"[^\w\s]", " ", text).split()
    return " ".join(w.lower() if w in {"AND", "OR", "NOT", "TO"} else w for w in words)


def fuse(rankings, k=RRF_K):
    """Reciprocal rank fusion: IDs ordered by the sum of 1 / (k + rank) over the rankings."""
    scores = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0) + 1 / (k + rank)
    return sorted(scores, key=lambda item: -scores[item])


def plain(value):
    """A Cypher value as JSON-able data; nodes and relationships become dicts of their properties."""
    if isinstance(value, Node):
        return {"labels": sorted(value.labels), **{k: plain(v) for k, v in value.items() if k not in HIDDEN}}
    if isinstance(value, Relationship):
        return {"type": value.type, **{k: plain(v) for k, v in value.items()}}
    if isinstance(value, Path):
        return {"nodes": [plain(n) for n in value.nodes], "relationships": [plain(r) for r in value.relationships]}
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)          # dates, durations, points


def truncate_rows(rows, max_chars=MAX_RESULT_CHARS):
    """(the leading rows that fit in max_chars of JSON, whether any were cut)."""
    kept, size = [], 2
    for row in rows:
        size += len(json.dumps(row, ensure_ascii=False)) + 2
        if size > max_chars:
            return kept, True
        kept.append(row)
    return kept, False


class GraphTools:
    def __init__(self, driver, embedder):
        self.driver, self.embedder = driver, embedder

    def call(self, name, arguments):
        """Run a tool from the model's call (arguments as a JSON string); the result as JSON."""
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return json.dumps({"error": "arguments are not valid JSON"})
        if name not in TOOLS:
            return json.dumps({"error": f"unknown tool {name!r}; the tools are {sorted(TOOLS)}"})
        schema = TOOLS[name]
        if not isinstance(args, dict) or set(schema["required"]) - set(args) or set(args) - set(schema["properties"]):
            return json.dumps({"error": f"{name} takes {sorted(schema['properties'])}"})
        return json.dumps(getattr(self, name)(**args), ensure_ascii=False)

    def _read(self, query, **params):
        with self.driver.session(default_access_mode=READ_ACCESS) as session:
            return session.execute_read(lambda tx: [r.data() for r in tx.run(query, **params)])

    def find_entity(self, name, limit=ENTITY_LIMIT):
        """Matches having every word of the name, else any word (a nickname, a misspelling)."""
        words = lucene_text(name).split()
        if not words:
            return {"error": "give a name with letters or digits"}
        rows = []
        for joiner in (" AND ", " OR "):
            rows = self._read(f"""
                MATCH (n) SEARCH n IN (FULLTEXT INDEX {NAME_INDEX} FOR $q LIMIT $limit) SCORE AS score
                RETURN labels(n)[0] AS label, coalesce(n.id, n.key, n.qid) AS id,
                       coalesce(n.label, n.name, n.title) AS name, n.reality AS reality, n.type AS type,
                       n.year AS year, n.aliases[..8] AS aliases,
                       COUNT {{ (n)-[:APPEARS_IN|ACTED_IN]->(:Title) }} AS titles,
                       COLLECT {{ MATCH (n)-[:APPEARS_IN|ACTED_IN]->(t:Title) RETURN t.title
                                  ORDER BY t.release_order LIMIT 3 }} AS for_example
                ORDER BY score DESC""", q=joiner.join(words), limit=limit)
            if rows or len(words) == 1:
                break
        return {"matches": [{k: v for k, v in r.items() if v not in (None, [])} for r in rows]}

    def run_cypher(self, query):
        query = query.strip().rstrip(";")
        try:
            with self.driver.session(default_access_mode=READ_ACCESS) as session:
                kind = session.run(f"EXPLAIN {query}").consume().query_type
                if kind != "r":
                    return {"error": "only read queries are allowed (no CREATE, MERGE, SET, DELETE, REMOVE or "
                                     "writing procedures)"}
                rows, more = session.execute_read(self._fetch, query)
        except Neo4jError as error:
            return {"error": f"{error.code}: {error.message}"}
        kept, cut = truncate_rows(rows)
        result = {"rows": kept}
        if more or cut:
            result["note"] = (f"only the first {len(kept)} rows are shown; aggregate, filter or LIMIT the query")
        return result

    @staticmethod
    @unit_of_work(timeout=CYPHER_TIMEOUT)
    def _fetch(tx, query):
        rows = []
        for record in tx.run(query):
            if len(rows) == ROW_LIMIT:
                return rows, True
            rows.append(plain(dict(record)))
        return rows, False

    def search_plots(self, text, limit=PASSAGE_LIMIT):
        vector = self.embedder.embed([text])[0]
        by_vector = [r["id"] for r in self._read(f"""
            MATCH (p:Passage) SEARCH p IN (VECTOR INDEX {VECTOR_INDEX} FOR $v LIMIT $n) SCORE AS s
            RETURN p.id AS id ORDER BY s DESC""", v=vector, n=CANDIDATES)]
        words = lucene_text(text)
        by_words = [r["id"] for r in self._read(f"""
            MATCH (p:Passage) SEARCH p IN (FULLTEXT INDEX {TEXT_INDEX} FOR $q LIMIT $n) SCORE AS s
            RETURN p.id AS id ORDER BY s DESC""", q=words, n=CANDIDATES)] if words else []
        ids = fuse([by_vector, by_words])[:limit]
        rows = {r["id"]: r for r in self._read("""
            MATCH (p:Passage)-[:FROM]->(t:Title) WHERE p.id IN $ids
            RETURN p.id AS id, t.title AS title, t.qid AS title_qid, p.heading AS heading,
                   p.episodes AS episodes, p.text AS text""", ids=ids)}
        return {"passages": [{k: v for k, v in rows[i].items() if k != "id" and v != []} for i in ids if i in rows]}
