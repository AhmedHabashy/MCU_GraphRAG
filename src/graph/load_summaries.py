"""Summary nodes: the kept summaries loaded into Neo4j (docs/rag_design.md, "Summary nodes").

Each summary becomes (:Summary {id: "<kind>:<id>"}) with its text and key facts.
- SUMMARIZES links it to what it describes: its Title, Character or Team; a season to its
  series' Title (with the season number); a group (series, phase, universe, saga, reality) to
  every Title it covers, through the summaries it was written from.
- PART_OF links each summary a group was written from to the group's summary (title -> phase ->
  saga, season -> title), so search can step from a broad summary down to narrower ones.

The summary files are the source of truth (processed_data/summaries/outputs). The load stops,
naming them, unless every summary is kept against its current input. It replaces all Summary
nodes, so running it twice changes nothing.
Run after src.graph.load_neo4j, src.graph.profiles and src.graph.summary_inputs:
    .venv\\Scripts\\python.exe -m src.graph.load_summaries
"""

import re

from src.graph.load_neo4j import run_batches
from src.graph.neo4j_db import connect
from src.graph.summary_status import summary_states

NODES = {"title": ("Title", "qid"), "character": ("Character", "id"), "team": ("Team", "id")}
SEASON_ID = re.compile(r"^(Q\d+)-s(\d+)$")      # as summary_inputs.title_inputs names a season


def summary_id(kind, id_):
    return f"{kind}:{id_}"


def members(inp):
    """[(kind, id)] of the summaries a group input was written from. A source is [kind, id] for
    a summary, or a title qid for a plot."""
    return [tuple(s) for s in inp["sources"] if isinstance(s, list)]


def kept(rows):
    """[(input, output)] from summary_states rows; raises naming every summary not kept."""
    waiting = [f"{inp['kind']} {inp['id']} ({st})" for _, inp, _, st, _ in rows if st != "kept"]
    if waiting:
        raise RuntimeError(f"{len(waiting)} summaries are not kept: {', '.join(waiting)}")
    return [(inp, out) for _, inp, out, _, _ in rows]


def summary_rows(items):
    """(nodes, SUMMARIZES rows by label, PART_OF rows) for [(input, output)]."""
    inputs = {(i["kind"], i["id"]): i for i, _ in items}

    def titles(kind, id_):
        if kind == "title":
            return [id_]
        if kind == "season":
            return [SEASON_ID.match(id_)[1]]
        return list(dict.fromkeys(q for k, i in members(inputs[(kind, id_)]) for q in titles(k, i)))

    nodes, links, part_of = [], {label: [] for label, _ in NODES.values()}, []
    for inp, out in items:
        kind, id_, sid = inp["kind"], inp["id"], summary_id(inp["kind"], inp["id"])
        nodes.append({"id": sid, "kind": kind, "name": out["name"], "level": inp["level"], "text": out["summary"],
                      "key_facts": [k["fact"] for k in out["key_facts"]],
                      "key_fact_cites": [k["cite"] for k in out["key_facts"]],
                      "input_hash": out["input_hash"], "writer": out["writer"]})
        if kind in ("character", "team"):
            links[NODES[kind][0]].append({"summary": sid, "target": id_, "season": None})
        else:
            season = int(SEASON_ID.match(id_)[2]) if kind == "season" else None
            links["Title"] += [{"summary": sid, "target": q, "season": season} for q in titles(kind, id_)]
        part_of += [{"from": summary_id(k, i), "to": sid} for k, i in members(inp)]
    return nodes, links, part_of


def load(session, nodes, links, part_of):
    session.run("CREATE CONSTRAINT summary_id IF NOT EXISTS FOR (n:Summary) REQUIRE n.id IS UNIQUE")
    session.run("MATCH (s:Summary) DETACH DELETE s")
    run_batches(session, "UNWIND $rows AS r CREATE (n:Summary) SET n = r", nodes)
    for label, key in NODES.values():       # labels and keys come from NODES, not the data
        run_batches(session, f"""UNWIND $rows AS r MATCH (s:Summary {{id: r.summary}}), (n:{label} {{{key}: r.target}})
                          CREATE (s)-[:SUMMARIZES {{season: r.season}}]->(n)""", links[label])
    run_batches(session, """UNWIND $rows AS r MATCH (a:Summary {id: r.from}), (b:Summary {id: r.to})
                     CREATE (a)-[:PART_OF]->(b)""", part_of)
    found = session.run("""MATCH (s:Summary) RETURN count(s) AS nodes,
                             COUNT { (:Summary)-[:SUMMARIZES]->() } AS links,
                             COUNT { (:Summary)-[:PART_OF]->(:Summary) } AS part_of""").single()
    expected = {"nodes": len(nodes), "links": sum(map(len, links.values())), "part_of": len(part_of)}
    if dict(found) != expected:     # a link whose end is missing from the graph is not created
        raise RuntimeError(f"Loaded {dict(found)}, expected {expected}")
    return expected


def main():
    rows = summary_rows(kept(summary_states()))
    with connect() as driver, driver.session() as session:
        counts = load(session, *rows)
    print(f"Loaded {counts['nodes']} summaries, {counts['links']} SUMMARIZES and {counts['part_of']} PART_OF links")


if __name__ == "__main__":
    main()
