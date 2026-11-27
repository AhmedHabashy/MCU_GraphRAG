"""The case board (docs/rag_design.md, "The front end"): the graph cards a question and its answer
name, and the links between them, each link with its evidence. No LLM.

Cards: every entity the question names (src.retrieval.local.entry_points, variants included),
then one per name the answer uses (a title first, then the best linked), MAX_CARDS in all; an answer's thing
(place, universe, object) with no link to the others is left out. Links: the graph's
relationships between two cards, one link per direction and kind (data or plot), carrying the
evidence of each relationship it stands for: a plot fact's quote, a cast credit's title, a wiki
membership's role.
"""

from src.graph.load_neo4j import KEYS
from src.retrieval.answer import without_citations
from src.retrieval.local import GraphReader

MAX_CARDS = 24
MAX_EVIDENCE = 8                  # per link
BOARD_ORDER = ("Title", "Team", "Person", "Character", "Thing")     # for one name the answer uses
HIDDEN = ["ACTED_IN", "SUMMARIZES", "FROM", "PART_OF"]     # ACTED_IN repeats PLAYS; the rest aren't story links
CARDS = """MATCH (n:{kind}) WHERE n.{key} IN $keys
RETURN elementId(n) AS id, n.{key} AS key, coalesce(n.title, n.label, n.name) AS label,
       n.reality AS reality, n.type AS type, n.year AS year, n.kind AS team_kind"""
LINKS = f"""MATCH (a) WHERE elementId(a) IN $ids
MATCH (a)-[r]->(b) WHERE elementId(b) IN $ids AND NOT type(r) IN {HIDDEN}
OPTIONAL MATCH (t:Title {{qid: r.title_qid}})
RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS type, coalesce(r.source, '') AS source_name,
       r.evidence AS evidence, t.title AS title, r.credited_as AS credited, r.role AS role, r.status AS status,
       r.shared_qid AS shared"""


def chosen(question_named, answer_named, answer, max_cards=MAX_CARDS):
    """The entry points to show: every one the question names (variants included), then one per
    name the answer (the text answer_named was found in) uses: the entity whose own name it is
    before those it is an alias of, then by BOARD_ORDER (a person before a character of the same
    name: answers name actors), then the best linked; none when the question's cards already
    have one of them."""
    cards = [c for c in question_named if c["kind"] in KEYS]
    keys = {(c["kind"], c["key"]) for c in cards}
    by_span = {}
    for c in answer_named:
        if c["kind"] in KEYS:
            by_span.setdefault(c["span"], []).append(c)
    for (start, end), named_there in by_span.items():
        if any((c["kind"], c["key"]) in keys for c in named_there):
            continue
        phrase = answer[start:end]
        best = min(named_there, key=lambda c: (c["names"][0] != phrase, BOARD_ORDER.index(c["kind"]), -c["weight"]))
        cards.append(best)
        keys.add((best["kind"], best["key"]))
    return cards[:max_cards]


def card(kind, row):
    """A card: what it is, its name, and the line under the name."""
    under = {"Title": f"{row['type']}, {row['year']}" if row["year"] else row["type"],
             "Character": row["reality"], "Team": f"{row['team_kind']}, {row['reality']}",
             "Thing": row["type"],
             "Person": ""}[kind]
    return {"id": row["id"], "kind": kind.lower(), "label": row["label"], "under": under or ""}


def evidence(r):
    """One relationship's evidence as a line."""
    if r["source_name"] == "plot":
        return f"{r['title']}: \"{r['evidence']}\"" if r["title"] else f"\"{r['evidence']}\""
    if r["type"] == "PLAYS":
        credit = f", credited as {r['credited'][0]}" if r["credited"] else ""
        return f"cast of {r['title']}{credit}" if r["title"] else "cast credit"
    if r["type"] == "MEMBER_OF":
        return f"{r['role'] or 'member'}, {r['status'] or 'status unknown'} ({r['source_name']} wiki)"
    if r["type"] == "VARIANT_OF":
        return f"Wikidata shared identity {r['shared']}" if r["shared"] else "variant link"
    return "credits and title data"


def links(rows):
    """One link per (source, target, plot or data): its label names every relationship type it
    stands for ("ally of · enemy of"), and its evidence lines say which type each is for when there
    are several. MAX_EVIDENCE lines per link."""
    grouped = {}
    for r in rows:
        plot = r["source_name"] == "plot"
        link = grouped.setdefault((r["source"], r["target"], plot), {
            "id": f"{r['source']}|{r['target']}|{int(plot)}", "source": r["source"], "target": r["target"],
            "types": [], "plot": plot, "lines": []})
        kind = r["type"].lower().replace("_", " ")
        if kind not in link["types"]:
            link["types"].append(kind)
        if (kind, evidence(r)) not in link["lines"]:
            link["lines"].append((kind, evidence(r)))
    return [{"id": link["id"], "source": link["source"], "target": link["target"], "plot": link["plot"],
             "label": " · ".join(link["types"]),
             "evidence": [f"{kind}: {line}" if len(link["types"]) > 1 else line
                          for kind, line in link["lines"]][:MAX_EVIDENCE]}
            for link in grouped.values()]


class Board(GraphReader):
    """(question, answer) -> {cards, links}."""

    def __call__(self, question, answer):
        asked = self.named(question)
        text = without_citations(answer).replace("*", "")
        picked = chosen(asked, self.named(text, skip_start=False), text)
        cards, from_question = [], set()
        for kind in KEYS:
            keys = [c["key"] for c in picked if c["kind"] == kind]
            if keys:
                rows = {r["key"]: r for r in self._read(CARDS.format(kind=kind, key=KEYS[kind]), keys=keys)}
                cards += [card(kind, rows[k]) for k in keys if k in rows]
                from_question |= {rows[c["key"]]["id"] for c in asked if c["kind"] == kind and c["key"] in rows}
        found = links(self._read(LINKS, ids=[c["id"] for c in cards])) if len(cards) > 1 else []
        return {"cards": linked(cards, found, from_question), "links": found}


def linked(cards, found, keep):
    """The cards to show: the question's (ids in keep), and the answer's, except a thing (a place,
    a universe, an object) that no link joins to the rest: those only clutter the board, while an
    unlinked person or character the answer names (the actors of a ranking) is still its subject."""
    ends = {x for link in found for x in (link["source"], link["target"])}
    return [c for c in cards if c["id"] in keep or c["id"] in ends or c["kind"] != "thing"]
