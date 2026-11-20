"""Load the built tables and the extracted plot facts into Neo4j (a full rebuild each run).

Nodes:  Title {qid}, Character {id}, Actor {key}, Team {id}, Thing {key}
        Thing = a fact end with no ID (Tesseract, Asgard, Team X): one per type, name and reality.
Edges:  (Character)-[:APPEARS_IN]->(Title)
        (Actor)-[:PLAYS {title_qid, credited_as}]->(Character)
        (Character)-[:VARIANT_OF {shared_qid}]->(Character)
        (Character)-[:MEMBER_OF {role, status, source, source_url}]->(Team)       (wiki infoboxes)
        (x)-[:<RELATION> {title_qid, episode, evidence, note, chunk, source: "plot"}]->(y)
            one per extracted fact; RELATION is one of check_extraction.RELATIONS.
An unlinked fact end is a Team when exactly one team in the title's reality has that name or
alias (the X-Men of X-Men '97), else a Thing.

Needs:  processed_data/ (titles, characters, teams, extraction/plots/outputs), Neo4j running
Run:    .venv\\Scripts\\python.exe -m src.graph.load_neo4j
"""

from src.graph.check_extraction import RELATIONS
from src.graph.neo4j_db import connect
from src.graph.prepare_extraction import OUTPUTS_DIR
from src.processing.build_characters import ALIASES_PATH, CHARACTERS_PATH, LINKS_PATH, PERFORMANCES_PATH
from src.processing.build_teams import MEMBERSHIPS_PATH, TEAMS_PATH
from src.processing.build_titles import RELEASE_ORDER_PATH, TIMELINE_PATH, TITLE_PHASES_PATH
from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.cast_matching import normalize_name
from src.source_data_collection.storage import read_csv, read_json

BATCH = 1000
KEYS = {"Title": "qid", "Character": "id", "Actor": "key", "Team": "id", "Thing": "key"}


def _split(value):
    return [v for v in value.split("|") if v]


def _by_qid(path):
    return {r["title_qid"]: r for r in read_csv(path)}


def title_rows(registry, release, phases, timeline):
    rows = []
    for t in registry:
        q = t["wikidata_qid"]
        r, p, tl = release.get(q, {}), phases.get(q, {}), timeline.get(q, {})
        rows.append({"qid": q, "title": t["title"], "type": t["type"], "year": int(t["year"]),
                     "universe": t["universe"], "reality": t["reality"], "tier": t["tier"],
                     "first_release_date": r.get("first_release_date", ""),
                     "release_order": int(r["release_order"]) if r.get("release_order") else None,
                     "chronological_order": int(tl["chronological_order"]) if tl.get("chronological_order") else None,
                     "phases": _split(p.get("phases", "")), "sagas": _split(p.get("sagas", ""))})
    return rows


def character_rows(characters, aliases):
    names = {}
    for a in aliases:
        names.setdefault(a["character_id"], []).append(a["alias"])
    return [{"id": c["character_id"], "base_qid": c["base_qid"], "reality": c["reality"], "label": c["label"],
             "identity_source": c["identity_source"], "species": _split(c["species"]),
             "aliases": sorted(set(names.get(c["character_id"], []))),
             "marvel_db_page": c["marvel_db_page"], "mcu_wiki_page": c["mcu_wiki_page"]} for c in characters]


def actor_key(performance):
    return performance["actor_qid"] or f"tmdb:{performance['tmdb_person_id']}"


def performance_rows(performances):
    """(actor nodes, PLAYS edges, APPEARS_IN edges), each once."""
    actors, plays, appears = {}, {}, set()
    for p in performances:
        cid = p["character_id"]
        if not cid:
            continue
        appears.add((cid, p["title_qid"]))
        if not (p["actor_qid"] or p["tmdb_person_id"]):
            continue
        key = actor_key(p)
        actors.setdefault(key, {"key": key, "qid": p["actor_qid"], "tmdb_id": p["tmdb_person_id"],
                                "name": p["actor_name"]})
        edge = plays.setdefault((key, cid, p["title_qid"]), {"actor": key, "character": cid,
                                                              "title_qid": p["title_qid"], "credited_as": []})
        if p["tmdb_character"] and p["tmdb_character"] not in edge["credited_as"]:
            edge["credited_as"].append(p["tmdb_character"])
    return (list(actors.values()), list(plays.values()),
            [{"character": c, "title": t} for c, t in sorted(appears)])


def group_name(name):
    """A group's name for matching: normalized, without a leading 'the' ("the Thunderbolts")."""
    normalized = normalize_name(name)
    return normalized.removeprefix("the ")


def team_index(teams):
    """(reality, group name of the team's name or alias) -> team IDs."""
    index = {}
    for t in teams:
        for name in [t["name"], *_split(t["aliases"])]:
            index.setdefault((t["reality"], group_name(name)), set()).add(t["team_id"])
    return index


GROUP_TYPES = {"team", "organization"}


def _end_type(fact, side):
    return "character" if side == "subject" else fact["object_type"]


def fact_end(fact, side, reality, team_ids, teams_by_name):
    """(label, key) of a fact's subject or object. An unlinked group (any subject, or an object
    typed team/organization) is the team of that name or alias in the title's reality, if one."""
    node_id, name = fact[f"{side}_id"], fact[f"{side}_name"]
    if node_id:
        return ("Team" if node_id in team_ids else "Character"), node_id
    if side == "subject" or fact["object_type"] in GROUP_TYPES:
        found = teams_by_name.get((reality, group_name(name)), set())
        if len(found) == 1:
            return "Team", next(iter(found))
    return "Thing", f"{_end_type(fact, side)}:{normalize_name(name)}@{reality}"


def fact_rows(outputs, realities, team_ids, teams_by_name):
    """(Thing nodes, fact edges by relation) from the extraction outputs ({chunk: output})."""
    things, edges = {}, {r: [] for r in RELATIONS}
    for chunk, output in outputs.items():
        reality = realities[output["title_qid"]]
        for fact in output["facts"]:
            ends = {}
            for side in ("subject", "object"):
                label, key = fact_end(fact, side, reality, team_ids, teams_by_name)
                ends[side] = (label, key)
                if label == "Thing":
                    things.setdefault(key, {"key": key, "name": fact[f"{side}_name"], "reality": reality,
                                            "type": _end_type(fact, side)})
            edges[fact["relation"]].append({
                "from_label": ends["subject"][0], "from": ends["subject"][1],
                "to_label": ends["object"][0], "to": ends["object"][1],
                "title_qid": output["title_qid"], "episode": fact["episode"], "evidence": fact["evidence"],
                "note": fact["note"], "chunk": chunk})
    return list(things.values()), edges


def _run(session, query, rows):
    for i in range(0, len(rows), BATCH):
        session.run(query, rows=rows[i:i + BATCH])


def load(session, data):
    session.run("MATCH (n) DETACH DELETE n")
    for label, key in KEYS.items():
        session.run(f"CREATE CONSTRAINT {label.lower()}_{key} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key} IS UNIQUE")
    for label, rows in (("Title", data["titles"]), ("Character", data["characters"]), ("Actor", data["actors"]),
                        ("Team", data["teams"]), ("Thing", data["things"])):
        _run(session, f"UNWIND $rows AS r CREATE (n:{label}) SET n = r", rows)
    _run(session, """UNWIND $rows AS r MATCH (c:Character {id: r.character}), (t:Title {qid: r.title})
                     CREATE (c)-[:APPEARS_IN]->(t)""", data["appears"])
    _run(session, """UNWIND $rows AS r MATCH (a:Actor {key: r.actor}), (c:Character {id: r.character})
                     CREATE (a)-[:PLAYS {title_qid: r.title_qid, credited_as: r.credited_as}]->(c)""", data["plays"])
    _run(session, """UNWIND $rows AS r MATCH (a:Character {id: r.from_id}), (b:Character {id: r.to_id})
                     CREATE (a)-[:VARIANT_OF {shared_qid: r.shared_qid}]->(b)""", data["variants"])
    _run(session, """UNWIND $rows AS r MATCH (c:Character {id: r.character_id}), (t:Team {id: r.team_id})
                     CREATE (c)-[:MEMBER_OF {role: r.role, status: r.status, source: r.source,
                                             source_url: r.source_url}]->(t)""", data["memberships"])
    for relation, rows in data["facts"].items():  # RELATION names come from a fixed list, not the data
        for (fl, tl) in {(r["from_label"], r["to_label"]) for r in rows}:
            _run(session, f"""UNWIND $rows AS r MATCH (a:{fl} {{{KEYS[fl]}: r.from}}), (b:{tl} {{{KEYS[tl]}: r.to}})
                              CREATE (a)-[:{relation} {{title_qid: r.title_qid, episode: r.episode,
                                  evidence: r.evidence, note: r.note, chunk: r.chunk, source: 'plot'}}]->(b)""",
                 [r for r in rows if (r["from_label"], r["to_label"]) == (fl, tl)])


def read_data():
    registry = read_csv(REGISTRY_PATH)
    teams = read_csv(TEAMS_PATH)
    actors, plays, appears = performance_rows(read_csv(PERFORMANCES_PATH))
    outputs = {p.stem: read_json(p) for p in sorted(OUTPUTS_DIR.glob("*.json"))}
    things, facts = fact_rows(outputs, {t["wikidata_qid"]: t["reality"] for t in registry},
                              {t["team_id"] for t in teams}, team_index(teams))
    return {
        "titles": title_rows(registry, _by_qid(RELEASE_ORDER_PATH), _by_qid(TITLE_PHASES_PATH), _by_qid(TIMELINE_PATH)),
        "characters": character_rows(read_csv(CHARACTERS_PATH), read_csv(ALIASES_PATH)),
        "actors": actors, "plays": plays, "appears": appears,
        "teams": [{"id": t["team_id"], "name": t["name"], "reality": t["reality"], "kind": t["kind"],
                   "aliases": _split(t["aliases"])} for t in teams],
        "things": things,
        "variants": [l for l in read_csv(LINKS_PATH) if l["relation"] == "variant"],
        "memberships": [m for m in read_csv(MEMBERSHIPS_PATH) if m["character_id"]],
        "facts": facts,
    }


def main():
    data = read_data()
    with connect() as driver, driver.session() as session:
        load(session, data)
        counts = session.run("MATCH (n) RETURN count(n) AS n").single()["n"], \
            session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
    facts = sum(len(rows) for rows in data["facts"].values())
    print(f"Loaded {counts[0]} nodes and {counts[1]} relationships ({facts} plot facts)")


if __name__ == "__main__":
    main()
