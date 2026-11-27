"""The aggregation tool (docs/rag_design.md, "Aggregation tool"): counts, rankings and averages
computed over the whole graph, for the questions whose answer needs a complete set ("who
directed the most", "which title grossed the least"). No LLM: the question's embedding picks the
views whose descriptions are closest to it; each view is a fixed read query over the whole graph,
so its rows rest on every title, character or person, and its header says over how many.

Each view gives a header and one line per row; the context holds the VIEWS_SHOWN closest views.
"""

from src.retrieval.embeddings import vectors_for
from src.retrieval.local import GraphReader, fit

VIEWS_SHOWN = 2


def _money(value):
    return f"${value:,.0f}" if value else "none"


def _titles(rows, key="titles"):
    return ", ".join(rows[key])


VIEWS = {
    "box_office": {
        "description": "Box office gross and budget of every title, ranked by gross; which title or film grossed "
                       "the most or the least, biggest budget, and whether sequels earn more than the film before",
        "query": """MATCH (t:Title) OPTIONAL MATCH (t)-[:FOLLOWS]->(p:Title)
                    RETURN t.title AS title, t.type AS type, t.year AS year, t.universe AS universe,
                           t.phases AS phases, t.box_office_usd AS gross, t.budget_usd AS budget,
                           p.title AS previous, p.box_office_usd AS previous_gross
                    ORDER BY coalesce(t.box_office_usd, -1) DESC, t.title""",
        "header": "Box office and budget of all {n} titles, highest gross first (US dollars; 'none' where unknown):",
        "line": lambda r: (f"{r['title']} ({r['type']}, {r['year']}, {r['universe']}; phases: {', '.join(r['phases']) or 'none'}): "
                           f"gross {_money(r['gross'])}; budget {_money(r['budget'])}"
                           + (f"; follows {r['previous']} (gross {_money(r['previous_gross'])})" if r["previous"] else "")),
    },
    "budget": {
        "description": "Production budget of every title, ranked: which film had the biggest or smallest budget",
        "query": """MATCH (t:Title) RETURN t.title AS title, t.type AS type, t.year AS year, t.budget_usd AS budget
                    ORDER BY coalesce(t.budget_usd, -1) DESC, t.title""",
        "header": "Budget of all {n} titles, biggest first (US dollars; 'none' where unknown):",
        "line": lambda r: f"{r['title']} ({r['type']}, {r['year']}): budget {_money(r['budget'])}",
    },
    "ratings": {
        "description": "TMDB rating of every title, ranked: the highest or lowest rated title, and the average "
                       "rating of the films in each phase",
        "query": """MATCH (t:Title) WHERE t.tmdb_votes > 0
                    RETURN t.title AS title, t.type AS type, t.year AS year, t.phases AS phases,
                           t.tmdb_rating AS rating, t.tmdb_votes AS votes
                    ORDER BY t.tmdb_rating DESC, t.title""",
        "header": "TMDB rating of all {n} released titles (those with TMDB votes), highest first:",
        "line": lambda r: (f"{r['title']} ({r['type']}, {r['year']}; phases: {', '.join(r['phases']) or 'none'}): "
                           f"TMDB {r['rating']} ({r['votes']} votes)"),
    },
    "phase_ratings": {
        "description": "Average TMDB rating of the films in each phase, and of the films in no phase",
        "query": """MATCH (t:Title {type: 'Film'}) WHERE t.tmdb_votes > 0
                    UNWIND (CASE WHEN size(t.phases) = 0 THEN ['no phase'] ELSE t.phases END) AS phase
                    RETURN phase, count(t) AS films, round(avg(t.tmdb_rating), 2) AS average ORDER BY phase""",
        "header": "Average TMDB rating of the released films (those with TMDB votes) in each phase ({n} groups; a film in "
                  "two phases counts in both):",
        "line": lambda r: f"{r['phase']}: {r['average']} over {r['films']} films",
    },
    "timeline": {
        "description": "In-universe setting years and order of every title, earliest first: which title is set "
                       "earliest, which titles are released after one but set before it, the in-universe order",
        "query": """MATCH (t:Title) WHERE t.start_year IS NOT NULL
                    RETURN t.title AS title, t.type AS type, t.year AS year, t.first_release_date AS released,
                           t.start_year AS start, t.end_year AS end, t.chronological_order AS chrono,
                           t.release_order AS release_order, t.universe AS universe
                    ORDER BY t.start_year, coalesce(t.chronological_order, 9999)""",
        "header": "Setting of all {n} titles with in-universe years, earliest first (negative years are BC):",
        "line": lambda r: (f"{r['title']} ({r['type']}, released {r['released'] or r['year']}, release order {r['release_order']}; "
                           f"{r['universe']}): set {r['start']} to {r['end']}"
                           + (f", in-universe order {r['chrono']}" if r["chrono"] is not None else "")),
    },
    "phases": {
        "description": "How many titles are in each MCU phase and which ones, and which titles are in no phase",
        "query": """MATCH (t:Title)
                    UNWIND (CASE WHEN size(t.phases) = 0 THEN ['no phase'] ELSE t.phases END) AS phase
                    WITH phase, t ORDER BY t.release_order
                    RETURN phase, count(t) AS count, collect(t.title + ' (' + t.universe + ')') AS titles ORDER BY phase""",
        "header": "Titles per phase over all titles, each with its universe ({n} groups; a title in two phases is listed "
                  "in both):",
        "line": lambda r: f"{r['phase']}: {r['count']} titles: {_titles(r)}",
    },
    "character_titles": {
        "description": "Characters ranked by the number of titles they appear in: which character appears in the most titles",
        "query": """MATCH (c:Character)-[:APPEARS_IN]->(t:Title)
                    WITH c, t ORDER BY t.release_order
                    WITH c, collect(t.title) AS titles ORDER BY size(titles) DESC, c.label LIMIT 25
                    RETURN c.label AS label, c.reality AS reality, size(titles) AS count, titles,
                           COLLECT { MATCH (p:Person)-[:PLAYS]->(c) RETURN DISTINCT p.name } AS actors""",
        "header": "The 25 characters in the most titles, counted over all characters and titles:",
        "line": lambda r: (f"{r['label']} [{r['reality']}] ({', '.join(r['actors']) or 'no actor'}): "
                           f"{r['count']} titles: {_titles(r)}"),
    },
    "actor_titles": {
        "description": "Actors ranked by the number of titles they act in, with how many of those credits are cameos: "
                       "which actor appears in the most titles",
        "query": """MATCH (p:Person)-[:ACTED_IN]->(t:Title)
                    WITH p, count(DISTINCT t) AS count ORDER BY count DESC, p.name LIMIT 25
                    RETURN p.name AS name, count,
                           COLLECT { MATCH (p)-[r:PLAYS]->(c:Character)
                                     WITH c, count(DISTINCT r.title_qid) AS n ORDER BY n DESC
                                     RETURN c.label + ' (' + toString(n) + ')' } AS characters""",
        "header": "The 25 actors in the most titles, counted over all people and titles, with the characters they play "
                  "(titles each):",
        "line": lambda r: f"{r['name']}: {r['count']} titles; as {', '.join(r['characters']) or 'no character'}",
    },
    "costars": {
        "description": "Characters ranked by how many other characters they share films with",
        "query": """MATCH (c:Character)-[:APPEARS_IN]->(t:Title {type: 'Film'})<-[:APPEARS_IN]-(o:Character) WHERE o <> c
                    WITH c, count(DISTINCT o) AS count ORDER BY count DESC, c.label LIMIT 20
                    RETURN c.label AS label, c.reality AS reality, count,
                           COLLECT { MATCH (p:Person)-[:PLAYS]->(c) RETURN DISTINCT p.name } AS actors""",
        "header": "The 20 characters who share films with the most other characters, counted over all films:",
        "line": lambda r: f"{r['label']} [{r['reality']}] ({', '.join(r['actors']) or 'no actor'}): {r['count']} other characters",
    },
    "directors": {
        "description": "Directors ranked by the number of films they directed: who directed the most films",
        "query": """MATCH (p:Person)-[:DIRECTED]->(t:Title {type: 'Film'})
                    WITH p, t ORDER BY t.release_order
                    WITH p, collect(t.title) AS titles ORDER BY size(titles) DESC, p.name LIMIT 20
                    RETURN p.name AS name, size(titles) AS count, titles""",
        "header": "The 20 directors of the most films, counted over all films:",
        "line": lambda r: f"{r['name']}: {r['count']} films: {_titles(r)}",
    },
    "actors_two_characters": {
        "description": "Actors who play two or more different characters (not variants of one character), with the titles",
        "query": """MATCH (p:Person)-[r:PLAYS]->(c:Character) MATCH (t:Title {qid: r.title_qid})
                    WITH p, c, collect(DISTINCT t.title + ' (' + toString(t.year) + ')'
                                       + CASE WHEN size(r.credited_as) > 0 THEN ' as "' + r.credited_as[0] + '"' ELSE '' END) AS titles
                    WITH p, collect({base: c.base_qid, text: c.label + ' [' + c.reality + ']: ' + reduce(s = '', x IN titles |
                                         s + CASE s WHEN '' THEN '' ELSE ', ' END + x),
                                     major: EXISTS { (:Summary {id: 'character:' + c.id}) } OR size(titles) > 1}) AS roles
                    WITH p, roles, reduce(s = [], x IN roles | CASE WHEN x.base IN s THEN s ELSE s + x.base END) AS bases
                    WHERE size(bases) > 1 AND any(x IN roles WHERE x.major)
                    RETURN p.name AS name, [x IN roles | x.text] AS roles, size(bases) AS characters
                    ORDER BY characters DESC, name""",
        "header": "Every actor who plays two or more different characters, at least one of them a main character or in "
                  "two titles ({n} actors; variants of one character count once):",
        "line": lambda r: f"{r['name']} ({r['characters']} characters): " + "; ".join(r["roles"]),
    },
}


def closest_views(scores, shown=VIEWS_SHOWN):
    """The names of the views with the highest scores."""
    return [name for name, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:shown]]


def view_block(name, rows):
    view = VIEWS[name]
    return "\n".join([f"## {view['header'].format(n=len(rows))}"] + [f"- {view['line'](r)}" for r in rows])


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm = (sum(x * x for x in a) * sum(y * y for y in b)) ** 0.5
    return dot / norm if norm else 0.0


class Views(GraphReader):
    """The views by name, read from the graph: what the answer step's aggregate tool returns."""

    def block(self, name):
        return view_block(name, self._read(VIEWS[name]["query"]))


class AggregateSearch(Views):
    """A strategy for src.retrieval.evaluation: (question, question vector) -> context text."""

    def __init__(self, driver, embedder=None):
        super().__init__(driver)
        if embedder is None:
            from src.retrieval.openrouter import from_env
            embedder = from_env()
        vectors, _ = vectors_for("views", [v["description"] for v in VIEWS.values()], embedder)
        self.view_vectors = dict(zip(VIEWS, vectors))

    def __call__(self, question, vector):
        names = closest_views({n: _cosine(vector, v) for n, v in self.view_vectors.items()})
        return fit([self.block(n) for n in names], [])
