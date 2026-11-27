"""Local search (docs/rag_design.md, "Local search"): the graph around what a question names, plus
what the indexes find by its words and meaning. No LLM: the only model call is the question's
embedding, made by the caller.

1. Entry points: names and aliases of titles, characters, people, teams and things (the name
   index), and the names of the group summaries (phases, sagas, universes, series, realities),
   that occur in the question as a whole phrase with the same capitals. Where matches overlap the
   longest wins; every entity sharing the winning phrase is kept (a name's variants).
2. One step from each: a title's header, summary, crew and whole cast, and last the cast's other
   titles; a character's profile and summary; a person's roles and crew credits; a team's wiki
   members (with the aliases that say more than their label) and summary; a group's
   summary and its titles' headers. Titles, characters, teams and things add their plot facts
   closest to the question.
3. Search: plot facts, passages and summaries, each by the keyword and the vector index, the two
   rankings fused by reciprocal rank.
When the question names two titles or two teams, what they share (characters in both casts,
members of both) comes first, worked out by the graph.
The context is cut to MAX_CONTEXT_CHARS: entry points first, in question order, each to a fair
share of the room (a block is cut at its own end); SEARCH_CHARS kept for the search hits. A
character's block also names who plays each of its variants.
"""

import re
from itertools import combinations

from src.graph.load_neo4j import KEYS
from src.graph.summary_inputs import fact_line

MAX_CONTEXT_CHARS = 32_000      # 20,000 cut multi-entity questions short in local runs 2 to 5
SEARCH_CHARS = 6_000            # kept for the search hits when entry points fill the rest
NAME_CANDIDATES = 500           # name-index hits checked for a whole-phrase match
FACTS_PER_ENTITY = 8
SEARCH_LIMITS = {"facts": 12, "passages": 3, "summaries": 3}
CANDIDATES = 50                 # per ranking, before fusing
RRF_K = 60
KIND_ORDER = ("Title", "Group", "Team", "Character", "Person", "Thing")
GROUP_KINDS = ("series", "phase", "universe", "saga", "reality")
CUT = "[cut]"


# --- pure helpers ---------------------------------------------------------------------------

def lucene_text(text):
    """Plain words for a full-text query: no Lucene syntax, operators lowercased into words."""
    words = re.sub(r"[^\w\s]", " ", text).split()
    return " ".join(w.lower() if w in {"AND", "OR", "NOT", "TO"} else w for w in words)


def fuse(rankings, k=RRF_K):
    """Reciprocal rank fusion: items ordered by the sum of 1 / (k + rank) over the rankings."""
    scores = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0) + 1 / (k + rank)
    return sorted(scores, key=lambda item: -scores[item])


def name_spans(question, names, skip_start=True):
    """[(start, end)] of every whole-phrase occurrence of the names, capitals as written; a hyphen
    joins words ("Earth" is not in "Earth-828"). "The X" also matches "the X", with the span of X
    alone, so it ties with an entity named X ("the Avengers": the team, not only the film). A
    one-word match at the question's start is skipped: its capital may only start the sentence
    (skip_start False for a text such as an answer, which often starts with a name)."""
    spans = set()
    for name in names:
        for phrase, skip in [(name, 0)] + ([(f"the {name[4:]}", 4)] if name.startswith("The ") else []):
            for m in re.finditer(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", question):
                if not (skip_start and m.start() == 0 and " " not in phrase):
                    spans.add((m.start() + skip, m.end()))
    return spans


def entry_points(question, candidates, skip_start=True):
    """The candidates ({kind, key, names, weight}) the question names: each at its longest span;
    overlapping spans give way to the longest; entities sharing a kept span are all kept. In
    question order, then by KIND_ORDER and weight."""
    best = {}
    for c in candidates:
        spans = name_spans(question, c["names"], skip_start)
        if spans:
            best[(c["kind"], c["key"])] = (max(spans, key=lambda s: (s[1] - s[0], -s[0])), c)
    kept_spans = []
    for span in sorted({s for s, _ in best.values()}, key=lambda s: (s[0] - s[1], s[0])):
        if all(span == k or span[1] <= k[0] or span[0] >= k[1] for k in kept_spans):
            kept_spans.append(span)
    chosen = [(s, c) for s, c in best.values() if s in kept_spans]
    chosen.sort(key=lambda sc: (sc[0][0], KIND_ORDER.index(sc[1]["kind"]), -sc[1]["weight"]))
    return [c for _, c in chosen]


def _money(value):
    return f"${value:,.0f}" if value else None


def title_line(t):
    """One title as a line: what it is, when it is released and set, where it belongs, and its numbers."""
    parts = [f"{t['type']}, released {t.get('first_release_date') or t['year']}"]
    if t.get("start_year") is not None:
        parts.append(f"set {t['start_year']} to {t['end_year']}")
    parts.append(f"universe {t['universe']}; reality {t['reality']}")
    parts.append("phases: " + (", ".join(t.get("phases") or []) or "none")
                 + ("; sagas: " + ", ".join(t["sagas"]) if t.get("sagas") else ""))
    order = f"release order {t['release_order']}"
    if t.get("chronological_order") is not None:
        order += f", in-universe order {t['chronological_order']}"
    parts.append(order)
    for label, value in (("box office", _money(t.get("box_office_usd"))), ("budget", _money(t.get("budget_usd"))),
                         ("runtime", f"{t['runtime_minutes']} min" if t.get("runtime_minutes") else None),
                         ("TMDB rating", f"{t['tmdb_rating']} ({t['tmdb_votes']} votes)" if t.get("tmdb_rating") else None)):
        if value:
            parts.append(f"{label} {value}")
    return f"{t['title']} [{t['qid']}] ({'; '.join(parts)})"


def _who(label, reality):
    return f"{label} [{reality}]" if reality else label


def title_block(row, facts):
    t = row["t"]
    lines = [f"## Title: {title_line(t)}"]
    for label, names in (("Follows", row["follows"]), ("Followed by", row["followed_by"]),
                         ("Directed by", row["directors"]), ("Written by", row["writers"])):
        if names:
            lines.append(f"{label}: {', '.join(names)}")
    if row["summary"]:
        lines.append(f"Summary: {row['summary']}")
    lines += _facts_lines(facts)
    if row["cast"]:
        other = {a["name"]: a["other"] for a in row["cast_elsewhere"]}
        lines.append("Characters (actors; their other titles), by billing:")
        lines += [cast_line(c, other) for c in row["cast"]]
    return "\n".join(lines)


def cast_line(character, other):
    """One cast entry: the character, each actor, and the actor's other titles in release order,
    by character ("also in" for the same character). One line each, so a cut drops the lowest
    billed first."""
    actors = []
    for name in character["actors"]:
        roles = {}
        for r in sorted(other.get(name, []), key=lambda r: r["order"]):
            roles.setdefault((r["character"], r["reality"]), []).append(r["title"])
        parts = [(f"also in {', '.join(titles)}" if (c, reality) == (character["label"], character["reality"])
                  else f"as {_who(c, reality)} in {', '.join(titles)}") for (c, reality), titles in roles.items()]
        actors.append(name + (f"; {'; '.join(parts)}" if parts else ""))
    return f"- {_who(character['label'], character['reality'])}" + (f" ({' | '.join(actors)})" if actors else "")


def other_names(label, aliases):
    """A character's aliases that say more than its label: not the label, nor a part of it
    ("Alexei" for Alexei Shostakov)."""
    return [a for a in aliases or [] if a not in label]


def character_block(row, facts):
    lines = [f"## Character: {row['profile']}"]
    played = [f"{_who(v['label'], v['reality'])}: {', '.join(v['actors'])}" for v in row["variants"] if v["actors"]]
    if played:
        lines.append(f"Variants' actors: {'; '.join(played)}")
    if row["summary"]:
        lines.append(f"Summary: {row['summary']}")
    return "\n".join(lines + _facts_lines(facts))


def person_block(row):
    lines = [f"## Person: {row['name']}" + (f" (born {row['born']})" if row["born"] else "")]
    roles = {}
    for r in row["roles"]:
        credit = f" as \"{'; '.join(r['credited'])}\"" if r["credited"] else ""
        roles.setdefault((r["character"], r["reality"]), []).append(f"{r['title']} ({r['year']}){credit}")
    lines += [f"Plays {_who(c, reality)} in: {', '.join(titles)}" for (c, reality), titles in roles.items()]
    for label, titles in (("Directed", row["directed"]), ("Wrote", row["wrote"]),
                          ("Other acting credits", row["other_credits"])):
        if titles:
            lines.append(f"{label}: {', '.join(titles)}")
    return "\n".join(lines)


def team_block(row, facts):
    lines = [f"## Team: {_who(row['name'], row['reality'])} ({row['kind']})"
             + (f", also known as {', '.join(row['aliases'])}" if row["aliases"] else "")]
    if row["summary"]:
        lines.append(f"Summary: {row['summary']}")
    lines += _facts_lines(facts)
    if row["members"]:
        lines.append("Members (wikis):")
        lines += [member_line(m) for m in row["members"]]
    return "\n".join(lines)


def member_line(m):
    """One team member: who, the aliases that say more than the label, and every role and status
    the wikis give. One line each, so a cut drops whole members."""
    names = other_names(m["label"], m["aliases"])
    return (f"- {_who(m['label'], m['reality'])}" + (f" (also {', '.join(names)})" if names else "")
            + f": {' / '.join(m['roles'])}")


def thing_block(row, facts):
    return "\n".join([f"## Thing: {_who(row['name'], row['reality'])} ({row['type']})"] + _facts_lines(facts))


def group_title_line(t):
    """A title in a group's list: what it is, when it is released and set (with its in-universe
    order: several titles share a year), where it belongs. Money and ratings are left to the
    aggregation tool."""
    setting = f"; set {t['start_year']} to {t['end_year']}" if t.get("start_year") is not None else ""
    if t.get("chronological_order") is not None:
        setting += f", in-universe order {t['chronological_order']}"
    return (f"{t['title']} [{t['qid']}] ({t['type']}, released {t.get('first_release_date') or t['year']}{setting}; "
            f"universe {t['universe']}; phases: {', '.join(t.get('phases') or []) or 'none'})")


def group_block(row):
    lines = [f"## {row['kind'].capitalize()}: {row['name']}", f"Summary: {row['text']}",
             f"Titles ({len(row['titles'])}, in release order):"]
    return "\n".join(lines + [f"- {group_title_line(t)}" for t in row["titles"]])


def shared_block(kind, a, b, rows):
    """What two named titles (their casts) or two named teams (their wiki members) share, worked out
    by the graph: an answer can't intersect two long lists reliably, and a cut list loses some."""
    what = "Characters in both casts" if kind == "Title" else "Characters who are members of both"
    names = [_who(r["label"], r["reality"]) for r in rows]
    return f"## {what}: {a} and {b} ({len(names)})\n" + (", ".join(names) or "none")


def shared_name(c):
    """A named title or team as its block's header writes it (titles with their QID, teams with
    their reality), so two titles of one name can be told apart."""
    if c["kind"] == "Title":
        return f"{c['names'][0]} [{c['key']}]"
    return _who(c["names"][0], c["key"].split("@", 1)[1])


def _facts_lines(facts):
    return (["Plot facts closest to the question:"] + [f"- {fact_line(f)}" for f in facts]) if facts else []


def shares(lengths, budget):
    """Each block's share of the budget: an equal share, and what a shorter block leaves unused
    goes to the others (so a long early block can't push out a later one)."""
    allowed, left = [0] * len(lengths), budget
    for n, i in enumerate(sorted(range(len(lengths)), key=lambda i: lengths[i])):
        allowed[i] = min(lengths[i], left // (len(lengths) - n))
        left -= allowed[i]
    return allowed


def fit(entries, hits, max_chars=MAX_CONTEXT_CHARS, search_chars=SEARCH_CHARS):
    """The context: entry blocks, each cut at its own end to its share (see shares), then the
    search hits in what is left; the hits keep search_chars when the entries would fill it all."""
    separators = 2 * max(len(entries) - 1, 0)
    budget = max_chars - (search_chars if hits else 0) - separators
    blocks = [_cut(e, share) for e, share in zip(entries, shares([len(e) for e in entries], budget))]
    return _cut("\n\n".join(blocks + hits), max_chars)


def _cut(text, max_chars):
    """The text cut to max_chars at the last line end or sentence end, marked as cut. A summary is
    one long line, so cutting at line ends alone would drop all of it."""
    if len(text) <= max_chars:
        return text
    kept = text[:max_chars - len(CUT) - 1]
    end = max(kept.rfind("\n"), kept.rfind(". ") + 1)
    return f"{kept[:end].rstrip() if end > 0 else ''}\n{CUT}".lstrip("\n")


# --- reading the graph ----------------------------------------------------------------------

CANDIDATES_QUERY = f"""
MATCH (n) SEARCH n IN (FULLTEXT INDEX entity_names FOR $q LIMIT {NAME_CANDIDATES}) SCORE AS score
RETURN labels(n)[0] AS kind, coalesce(n.qid, n.id, n.key) AS key,
       [x IN [n.title, n.label, n.name] + coalesce(n.aliases, []) WHERE x IS NOT NULL] AS names,
       COUNT {{ (n)-[:APPEARS_IN|ACTED_IN|PLAYS|MEMBER_OF]-() }} AS weight"""
FACT_FIELDS = """r.title_qid AS title_qid, t.title AS title, r.episode AS episode,
       coalesce(startNode(r).label, startNode(r).name, startNode(r).title) AS subject, type(r) AS relation,
       coalesce(endNode(r).label, endNode(r).name, endNode(r).title) AS object, r.evidence AS evidence, r.note AS note"""
TITLE_FACTS = f"""MATCH ()-[r]->() WHERE r.source = 'plot' AND r.title_qid = $key MATCH (t:Title {{qid: r.title_qid}})
       WITH r, t ORDER BY vector.similarity.cosine(r.embedding, $v) DESC LIMIT $n RETURN {FACT_FIELDS}"""
NODE_FACTS = """MATCH (x:{label} {{{key}: $key}})-[r]-() WHERE r.source = 'plot' MATCH (t:Title {{qid: r.title_qid}})
       WITH DISTINCT r, t ORDER BY vector.similarity.cosine(r.embedding, $v) DESC LIMIT $n RETURN """ + FACT_FIELDS
TITLE = """MATCH (t:Title {qid: $key}) OPTIONAL MATCH (s:Summary {id: 'title:' + t.qid})
RETURN t {.*} AS t, s.text AS summary,
  COLLECT { MATCH (t)-[:FOLLOWS]->(p:Title) RETURN p.title } AS follows,
  COLLECT { MATCH (n:Title)-[:FOLLOWS]->(t) RETURN n.title } AS followed_by,
  COLLECT { MATCH (p:Person)-[:DIRECTED]->(t) RETURN p.name } AS directors,
  COLLECT { MATCH (p:Person)-[:WROTE]->(t) RETURN p.name } AS writers,
  COLLECT { MATCH (c:Character)-[:APPEARS_IN]->(t)
            OPTIONAL MATCH (p:Person)-[r:PLAYS {title_qid: t.qid}]->(c)
            WITH c, collect(DISTINCT p.name) AS actors, min(r.billing_order) AS billing
            RETURN {label: c.label, reality: c.reality, actors: actors, billing: coalesce(billing, 9999)}
            ORDER BY billing, c.label } AS cast,
  COLLECT { MATCH (p:Person)-[r:PLAYS {title_qid: t.qid}]->(:Character)
            WITH p, min(r.billing_order) AS billing
            WITH p, billing, COLLECT { MATCH (p)-[o:PLAYS]->(c:Character) WHERE o.title_qid <> t.qid
                                       MATCH (other:Title {qid: o.title_qid})
                                       RETURN DISTINCT {title: other.title, order: other.release_order,
                                                        character: c.label, reality: c.reality} } AS other
            WHERE size(other) > 0
            RETURN {name: p.name, billing: coalesce(billing, 9999), other: other} AS a
            ORDER BY a.billing, a.name } AS cast_elsewhere"""
CHARACTER = """MATCH (c:Character {id: $key}) OPTIONAL MATCH (s:Summary {id: 'character:' + c.id})
RETURN c.profile AS profile, s.text AS summary,
  COLLECT { MATCH (c)-[v:VARIANT_OF]-(o:Character) WHERE v.source IS NULL WITH DISTINCT o
            RETURN {label: o.label, reality: o.reality,
                    actors: COLLECT { MATCH (p:Person)-[:PLAYS]->(o) RETURN DISTINCT p.name }} AS v
            ORDER BY v.label } AS variants"""
PERSON = """MATCH (p:Person {key: $key})
RETURN p.name AS name, p.birth_date AS born,
  COLLECT { MATCH (p)-[r:PLAYS]->(c:Character) MATCH (t:Title {qid: r.title_qid})
            RETURN {character: c.label, reality: c.reality, title: t.title, year: t.year, credited: r.credited_as}
            ORDER BY t.release_order } AS roles,
  COLLECT { MATCH (p)-[:DIRECTED]->(t:Title) RETURN t.title ORDER BY t.release_order } AS directed,
  COLLECT { MATCH (p)-[:WROTE]->(t:Title) RETURN t.title ORDER BY t.release_order } AS wrote,
  COLLECT { MATCH (p)-[:ACTED_IN]->(t:Title) WHERE NOT EXISTS { (p)-[:PLAYS {title_qid: t.qid}]->() }
            RETURN t.title ORDER BY t.release_order } AS other_credits"""
TEAM = """MATCH (t:Team {id: $key}) OPTIONAL MATCH (s:Summary {id: 'team:' + t.id})
RETURN t.name AS name, t.reality AS reality, t.kind AS kind, t.aliases AS aliases, s.text AS summary,
  COLLECT { MATCH (c:Character)-[m:MEMBER_OF]->(t) WHERE m.source <> 'plot'
            WITH c, collect(DISTINCT coalesce(m.role, 'member') + ', ' + coalesce(m.status, 'status unknown')) AS roles
            RETURN {label: c.label, reality: c.reality, aliases: c.aliases, roles: roles} AS m
            ORDER BY m.label } AS members"""
SHARED = {
    "Title": """MATCH (:Title {qid: $a})<-[:APPEARS_IN]-(c:Character)-[:APPEARS_IN]->(:Title {qid: $b})
                RETURN DISTINCT c.label AS label, c.reality AS reality ORDER BY label, reality""",
    "Team": """MATCH (:Team {id: $a})<-[m:MEMBER_OF]-(c:Character)-[n:MEMBER_OF]->(:Team {id: $b})
               WHERE m.source <> 'plot' AND n.source <> 'plot'
               RETURN DISTINCT c.label AS label, c.reality AS reality ORDER BY label, reality""",
}
THING = "MATCH (t:Thing {key: $key}) RETURN t.name AS name, t.reality AS reality, t.type AS type"
GROUP = """MATCH (s:Summary {id: $key})
RETURN s.kind AS kind, s.name AS name, s.text AS text,
  COLLECT { MATCH (s)-[:SUMMARIZES]->(t:Title) RETURN t {.*} AS t ORDER BY t.release_order } AS titles"""
GROUP_NAMES = f"""MATCH (s:Summary) WHERE s.kind IN {list(GROUP_KINDS)}
RETURN 'Group' AS kind, s.id AS key, [s.name] AS names, COUNT {{ (s)-[:SUMMARIZES]->() }} AS weight"""
SEARCHES = {
    "facts": ("MATCH ()-[n]->() SEARCH n IN (VECTOR INDEX evidence_embedding FOR $v LIMIT $n) SCORE AS s "
              "RETURN elementId(n) AS id ORDER BY s DESC",
              "CALL db.index.fulltext.queryRelationships('evidence_text', $q, {limit: $n}) YIELD relationship "
              "RETURN elementId(relationship) AS id"),
    "passages": ("MATCH (n:Passage) SEARCH n IN (VECTOR INDEX passage_embedding FOR $v LIMIT $n) SCORE AS s "
                 "RETURN n.id AS id ORDER BY s DESC",
                 "MATCH (n:Passage) SEARCH n IN (FULLTEXT INDEX passage_text FOR $q LIMIT $n) SCORE AS s "
                 "RETURN n.id AS id ORDER BY s DESC"),
    "summaries": ("MATCH (n:Summary) SEARCH n IN (VECTOR INDEX summary_embedding FOR $v LIMIT $n) SCORE AS s "
                  "RETURN n.id AS id ORDER BY s DESC",
                  "MATCH (n:Summary) SEARCH n IN (FULLTEXT INDEX summary_text FOR $q LIMIT $n) SCORE AS s "
                  "RETURN n.id AS id ORDER BY s DESC"),
}
HITS = {
    "facts": f"""UNWIND $ids AS id MATCH ()-[r]->() WHERE elementId(r) = id MATCH (t:Title {{qid: r.title_qid}})
                 RETURN id, {FACT_FIELDS}""",
    "passages": "UNWIND $ids AS id MATCH (n:Passage {id: id}) RETURN id, n.heading AS heading, n.text AS text",
    "summaries": "UNWIND $ids AS id MATCH (n:Summary {id: id}) RETURN id, n.kind AS kind, n.name AS name, n.text AS text",
}


class GraphReader:
    """What every strategy shares: read queries, the entry points a question names, and fused
    search."""

    def __init__(self, driver):
        self.driver = driver
        self.groups = self._read(GROUP_NAMES)

    def _read(self, query, **params):
        with self.driver.session() as session:
            return session.execute_read(lambda tx: [r.data() for r in tx.run(query, **params)])

    def named(self, question, skip_start=True):
        """The entities and groups the question names (see entry_points)."""
        words = lucene_text(question)
        return entry_points(question, (self._read(CANDIDATES_QUERY, q=words) if words else []) + self.groups,
                            skip_start)

    def searched(self, kind, question, vector):
        """Ids of kind ("facts", "passages", "summaries") by the keyword and vector rankings fused."""
        words = lucene_text(question)
        by_vector, by_words = SEARCHES[kind]
        rankings = [[r["id"] for r in self._read(by_vector, v=vector, n=CANDIDATES)]]
        if words:
            rankings.append([r["id"] for r in self._read(by_words, q=words, n=CANDIDATES)])
        return fuse(rankings)


class LocalSearch(GraphReader):
    """A strategy for src.retrieval.evaluation: (question, question vector) -> context text."""

    def __call__(self, question, vector):
        named = self.named(question)
        entries, shown = self._shared(named), set()
        for c in named:
            block, lines = self._block(c, vector)
            entries.append(block)
            shown |= lines
        return fit(entries, self._search(question, vector, shown))

    def _shared(self, named):
        """A shared_block for each pair of named titles and each pair of named teams; first, as
        they are short and exact."""
        blocks = []
        for kind in SHARED:
            of_kind = [c for c in named if c["kind"] == kind]
            for a, b in combinations(of_kind, 2):
                rows = self._read(SHARED[kind], a=a["key"], b=b["key"])
                blocks.append(shared_block(kind, shared_name(a), shared_name(b), rows))
        return blocks

    def _facts(self, c, vector):
        if c["kind"] == "Title":
            return self._read(TITLE_FACTS, key=c["key"], v=vector, n=FACTS_PER_ENTITY)
        if c["kind"] in ("Character", "Team", "Thing"):
            return self._read(NODE_FACTS.format(label=c["kind"], key=KEYS[c["kind"]]),
                              key=c["key"], v=vector, n=FACTS_PER_ENTITY)
        return []

    def _block(self, c, vector):
        """(the entry's block, the fact lines and summary ids it shows)."""
        facts = list({fact_line(f): f for f in self._facts(c, vector)}.values())
        shown = {fact_line(f) for f in facts}
        kind, key = c["kind"], c["key"]
        if kind == "Title":
            return title_block(self._read(TITLE, key=key)[0], facts), shown | {f"title:{key}"}
        if kind == "Character":
            return character_block(self._read(CHARACTER, key=key)[0], facts), shown | {f"character:{key}"}
        if kind == "Person":
            return person_block(self._read(PERSON, key=key)[0]), shown
        if kind == "Team":
            return team_block(self._read(TEAM, key=key)[0], facts), shown | {f"team:{key}"}
        if kind == "Thing":
            return thing_block(self._read(THING, key=key)[0], facts), shown
        return group_block(self._read(GROUP, key=key)[0]), shown | {key}

    def _search(self, question, vector, shown):
        """The search hits not already shown: plot facts, passages, summaries."""
        sections = []
        for kind in SEARCHES:
            rows = self._read(HITS[kind], ids=self.searched(kind, question, vector))
            if kind == "facts":
                lines = [fact_line(r) for r in rows]
                lines = [line for line in dict.fromkeys(lines) if line not in shown][:SEARCH_LIMITS[kind]]
                if lines:
                    sections.append("\n".join(["## Plot facts found by search"] + [f"- {x}" for x in lines]))
            elif kind == "passages":
                sections += [f"## Plot passage: {r['heading']}\n{r['text']}" for r in rows[:SEARCH_LIMITS[kind]]]
            else:
                sections += [f"## Summary ({r['kind']}): {r['name']}\n{r['text']}"
                             for r in rows if r["id"] not in shown][:SEARCH_LIMITS[kind]]
        return sections
