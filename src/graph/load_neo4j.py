"""Load the built tables and the extracted plot facts into Neo4j (a full rebuild each run).

Nodes:  Title {qid}, Character {id}, Person {key}, Team {id}, Thing {key}
        Person = an actor, director or writer: key is the Wikidata QID, else "tmdb:<TMDB id>".
        Thing = a fact end that is no Title, Character or Team (Tesseract, Asgard, Team X):
                one per type, name and reality.
        Title money: Wikidata's US dollars, else TMDB's (*_source says which); rating: TMDB's.
        Title years: in-universe start/end year, MCU wiki's, else Wikipedia's (negative = BC).
Edges:  (Character)-[:APPEARS_IN]->(Title)
        (Person)-[:PLAYS {title_qid, credited_as, billing_order}]->(Character)
        (Person)-[:ACTED_IN]->(Title)           every credit, also those linked to no character
        (Person)-[:DIRECTED]->(Title), (Person)-[:WROTE]->(Title)         (Wikidata)
        (Title)-[:FOLLOWS]->(Title)             the title it follows in its series (Wikidata)
        (Character)-[:VARIANT_OF {shared_qid}]->(Character)
        (Character)-[:MEMBER_OF {role, status, source, source_url}]->(Team)       (wiki infoboxes)
        (x)-[:<RELATION> {title_qid, episode, evidence, note, chunk, source: "plot"}]->(y)
            one per extracted fact; RELATION is one of check_extraction.RELATIONS.
An unlinked fact end (a name without an ID) is the Team, or for a character the Character, with
that name in the title's reality when exactly one has it (the X-Men of X-Men '97; Natalie
Rushman is Natasha Romanoff); else a Thing.
Indexes: a uniqueness constraint per node key, and the full-text index NAME_INDEX over names and
aliases. Plot passages are loaded afterwards by src.retrieval.passages (this run deletes them).

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
from src.source_data_collection.collect_title_details import (
    ACTOR_BIRTHS_PATH, TITLE_DETAILS_PATH, TMDB_BIRTHDAYS_PATH,
)
from src.source_data_collection.collect_title_stats import TMDB_STATS_PATH, WIKIDATA_MONEY_PATH
from src.source_data_collection.cast_matching import normalize_name
from src.source_data_collection.storage import read_csv, read_json

BATCH = 1000
KEYS = {"Title": "qid", "Character": "id", "Person": "key", "Team": "id", "Thing": "key"}
NAME_INDEX = "entity_names"     # full-text over every node's names, for src.retrieval.tools.find_entity


def _split(value):
    return [v for v in value.split("|") if v]


def _by_qid(path):
    return {r["title_qid"]: r for r in read_csv(path)}


def _int(value):
    return int(float(value)) if value not in ("", None) else None


def first_of(*sources):
    """(value, source name) of the first source that has a value: sources are (value, name)."""
    return next(((v, name) for v, name in sources if v is not None), (None, ""))


def title_rows(registry, release, phases, timeline, money, stats):
    rows = []
    for t in registry:
        q = t["wikidata_qid"]
        r, p, tl, m, s = release.get(q, {}), phases.get(q, {}), timeline.get(q, {}), money.get(q, {}), stats.get(q, {})
        box_office, box_office_source = first_of((_int(m.get("box_office_usd")), "wikidata"),
                                                 (_int(s.get("revenue_usd")), "tmdb"))
        budget, budget_source = first_of((_int(m.get("cost_usd")), "wikidata"), (_int(s.get("budget_usd")), "tmdb"))
        runtime, _ = first_of((_int(m.get("duration_minutes")), "wikidata"), (_int(s.get("runtime_minutes")), "tmdb"))
        mcu = (_int(tl.get("mcu_wiki_start_year")), _int(tl.get("mcu_wiki_end_year")))
        wikipedia = (_int(tl.get("wikipedia_start_year")), _int(tl.get("wikipedia_end_year")))
        years, years_source = first_of((mcu if mcu[0] is not None else None, "mcu_wiki"),
                                       (wikipedia if wikipedia[0] is not None else None, "wikipedia"))
        rows.append({"qid": q, "title": t["title"], "type": t["type"], "year": int(t["year"]),
                     "universe": t["universe"], "reality": t["reality"], "tier": t["tier"],
                     "first_release_date": r.get("first_release_date", ""),
                     "release_order": _int(r.get("release_order")),
                     "chronological_order": _int(tl.get("chronological_order")),
                     "start_year": years[0] if years else None, "end_year": years[1] if years else None,
                     "years_source": years_source,
                     "phases": _split(p.get("phases", "")), "sagas": _split(p.get("sagas", "")),
                     "box_office_usd": box_office, "box_office_source": box_office_source,
                     "budget_usd": budget, "budget_source": budget_source, "runtime_minutes": runtime,
                     "tmdb_rating": float(s["vote_average"]) if s.get("vote_average") else None,
                     "tmdb_votes": _int(s.get("vote_count"))})
    return rows


def character_rows(characters, aliases):
    names = {}
    for a in aliases:
        names.setdefault(a["character_id"], []).append(a["alias"])
    return [{"id": c["character_id"], "base_qid": c["base_qid"], "reality": c["reality"], "label": c["label"],
             "identity_source": c["identity_source"], "species": _split(c["species"]),
             "aliases": sorted(set(names.get(c["character_id"], []))),
             "marvel_db_page": c["marvel_db_page"], "mcu_wiki_page": c["mcu_wiki_page"]} for c in characters]


def person_key(qid, tmdb_id):
    return qid or f"tmdb:{tmdb_id}"


def performance_rows(performances):
    """(people, PLAYS edges, APPEARS_IN edges, ACTED_IN edges), each once. ACTED_IN counts every
    credit with a known person, also those linked to no character (most of Stan Lee's cameos)."""
    people, plays, appears, acted = {}, {}, set(), set()
    for p in performances:
        cid, has_person = p["character_id"], bool(p["actor_qid"] or p["tmdb_person_id"])
        if cid:
            appears.add((cid, p["title_qid"]))
        if not has_person:
            continue
        key = person_key(p["actor_qid"], p["tmdb_person_id"])
        person = people.setdefault(key, {"key": key, "qid": p["actor_qid"], "tmdb_id": p["tmdb_person_id"],
                                         "name": p["actor_name"]})
        person["tmdb_id"] = person["tmdb_id"] or p["tmdb_person_id"]
        acted.add((key, p["title_qid"]))
        if not cid:
            continue
        edge = plays.setdefault((key, cid, p["title_qid"]), {"person": key, "character": cid, "title_qid": p["title_qid"],
                                                              "credited_as": [], "billing_order": None})
        if p["tmdb_character"] and p["tmdb_character"] not in edge["credited_as"]:
            edge["credited_as"].append(p["tmdb_character"])
        billing = _int(p["billing_order"])
        if billing is not None and (edge["billing_order"] is None or billing < edge["billing_order"]):
            edge["billing_order"] = billing
    return (people, list(plays.values()), [{"character": c, "title": t} for c, t in sorted(appears)],
            [{"person": k, "title": t} for k, t in sorted(acted)])


def crew_rows(details, people):
    """DIRECTED and WROTE edges from Wikidata's title details; adds crew members to `people`."""
    edges = {"DIRECTED": [], "WROTE": []}
    for d in details:
        for relation, qids, names in (("DIRECTED", d["director_qids"], d["director_names"]),
                                      ("WROTE", d["writer_qids"], d["writer_names"])):
            for qid, name in zip(_split(qids), _split(names), strict=True):
                people.setdefault(qid, {"key": qid, "qid": qid, "tmdb_id": "", "name": name})
                edges[relation].append({"person": qid, "title": d["title_qid"]})
    return edges


def birth_dates(people, wikidata_births, tmdb_birthdays):
    """Set each person's birth_date: Wikidata's when it gives one date, else TMDB's."""
    by_qid = {r["actor_qid"]: _split(r["birth_dates"]) for r in wikidata_births if r["actor_qid"]}
    by_tmdb = {r["tmdb_person_id"]: r["birthday"] for r in tmdb_birthdays if r["birthday"]}
    for person in people.values():
        wikidata = by_qid.get(person["qid"], [])
        person["birth_date"] = wikidata[0] if len(wikidata) == 1 else by_tmdb.get(person["tmdb_id"], "")


def follows_rows(details):
    """(title)-[:FOLLOWS]->(the title it follows), both in the registry."""
    in_scope = {d["title_qid"] for d in details}
    return [{"title": d["title_qid"], "previous": prev} for d in details
            for prev in _split(d["follows_qids"]) if prev in in_scope]


def group_name(name):
    """A group's name for matching: normalized, without a leading 'the' ("the Thunderbolts")."""
    normalized = normalize_name(name)
    return normalized.removeprefix("the ")


def name_index(rows, name_field):
    """Two indexes of graph rows (Team or Character), (reality, group name) -> IDs: one by the
    row's own name (`name_field`), then one by its aliases."""
    own, aliases = {}, {}
    for r in rows:
        own.setdefault((r["reality"], group_name(r[name_field])), set()).add(r["id"])
        for alias in r["aliases"]:
            aliases.setdefault((r["reality"], group_name(alias)), set()).add(r["id"])
    return own, aliases


def unique_match(index, reality, name):
    """The one ID of that name in the reality: by own name, else by alias. None when the first
    index that knows the name has several IDs for it (five characters named Loki)."""
    for by_name in index:
        found = by_name.get((reality, group_name(name)), set())
        if found:
            return next(iter(found)) if len(found) == 1 else None
    return None


GROUP_TYPES = {"team", "organization"}
DEFAULT_TYPE = "character"   # a subject's type; also what extraction gives most unknown names


def _end_type(fact, side):
    return DEFAULT_TYPE if side == "subject" else fact["object_type"]


def fact_end(fact, side, reality, team_ids, teams, characters):
    """(label, ID) of a fact's subject or object; ID is None for a Thing. An unlinked end is the
    team (if a subject or typed team/organization) or else the character (if typed character)
    with that name in the title's reality, when exactly one has it (see unique_match)."""
    node_id, name, end_type = fact[f"{side}_id"], fact[f"{side}_name"], _end_type(fact, side)
    if node_id:
        return ("Team" if node_id in team_ids else "Character"), node_id
    if side == "subject" or end_type in GROUP_TYPES:
        if team := unique_match(teams, reality, name):
            return "Team", team
    if end_type == DEFAULT_TYPE:
        if character := unique_match(characters, reality, name):
            return "Character", character
    return "Thing", None


def thing_type(end_type, other_types):
    """A Thing's type. The default type gives way to the one other type the same name has in the
    reality ("Ravagers" as a subject and as an organization are one organization)."""
    return next(iter(other_types)) if end_type == DEFAULT_TYPE and len(other_types) == 1 else end_type


def fact_rows(outputs, realities, team_ids, teams, characters):
    """(Thing nodes, fact edges by relation) from the extraction outputs ({chunk: output});
    `teams` and `characters` are name_index results."""
    resolved, other_types = [], {}
    for chunk, output in outputs.items():
        reality = realities[output["title_qid"]]
        for fact in output["facts"]:
            ends = {side: fact_end(fact, side, reality, team_ids, teams, characters) for side in ("subject", "object")}
            for side, other in (("subject", "object"), ("object", "subject")):
                if not fact[f"{side}_id"] and ends[side][1] is not None and ends[side][1] == ends[other][1]:
                    ends[side] = ("Thing", None)   # a name for the other end itself: a cover identity, a form
            for side, (label, _) in ends.items():
                if label == "Thing" and _end_type(fact, side) != DEFAULT_TYPE:
                    other_types.setdefault((group_name(fact[f"{side}_name"]), reality), set()).add(
                        _end_type(fact, side))
            resolved.append((chunk, output["title_qid"], reality, fact, ends))
    things, edges = {}, {r: [] for r in RELATIONS}
    for chunk, title_qid, reality, fact, ends in resolved:
        for side, (label, node_id) in ends.items():
            if label == "Thing":
                name = group_name(fact[f"{side}_name"])
                kind = thing_type(_end_type(fact, side), other_types.get((name, reality), set()))
                node_id = f"{kind}:{name}@{reality}"
                things.setdefault(node_id, {"key": node_id, "name": fact[f"{side}_name"], "reality": reality,
                                            "type": kind})
            ends[side] = (label, node_id)
        edges[fact["relation"]].append({
            "from_label": ends["subject"][0], "from": ends["subject"][1],
            "to_label": ends["object"][0], "to": ends["object"][1],
            "title_qid": title_qid, "episode": fact["episode"], "evidence": fact["evidence"],
            "note": fact["note"], "chunk": chunk})
    return list(things.values()), edges


def run_batches(session, query, rows):
    for i in range(0, len(rows), BATCH):
        session.run(query, rows=rows[i:i + BATCH])


def load(session, data):
    session.run("MATCH (n) DETACH DELETE n")
    for label, key in KEYS.items():
        session.run(f"CREATE CONSTRAINT {label.lower()}_{key} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key} IS UNIQUE")
    session.run(f"CREATE FULLTEXT INDEX {NAME_INDEX} IF NOT EXISTS FOR (n:{'|'.join(KEYS)}) "
                "ON EACH [n.title, n.label, n.name, n.aliases]")
    for label, rows in (("Title", data["titles"]), ("Character", data["characters"]), ("Person", data["people"]),
                        ("Team", data["teams"]), ("Thing", data["things"])):
        run_batches(session, f"UNWIND $rows AS r CREATE (n:{label}) SET n = r", rows)
    run_batches(session, """UNWIND $rows AS r MATCH (c:Character {id: r.character}), (t:Title {qid: r.title})
                     CREATE (c)-[:APPEARS_IN]->(t)""", data["appears"])
    run_batches(session, """UNWIND $rows AS r MATCH (p:Person {key: r.person}), (c:Character {id: r.character})
                     CREATE (p)-[:PLAYS {title_qid: r.title_qid, credited_as: r.credited_as,
                                         billing_order: r.billing_order}]->(c)""", data["plays"])
    run_batches(session, """UNWIND $rows AS r MATCH (p:Person {key: r.person}), (t:Title {qid: r.title})
                     CREATE (p)-[:ACTED_IN]->(t)""", data["acted_in"])
    for relation in ("DIRECTED", "WROTE"):
        run_batches(session, f"""UNWIND $rows AS r MATCH (p:Person {{key: r.person}}), (t:Title {{qid: r.title}})
                          CREATE (p)-[:{relation}]->(t)""", data["crew"][relation])
    run_batches(session, """UNWIND $rows AS r MATCH (t:Title {qid: r.title}), (p:Title {qid: r.previous})
                     CREATE (t)-[:FOLLOWS]->(p)""", data["follows"])
    run_batches(session, """UNWIND $rows AS r MATCH (a:Character {id: r.from_id}), (b:Character {id: r.to_id})
                     CREATE (a)-[:VARIANT_OF {shared_qid: r.shared_qid}]->(b)""", data["variants"])
    run_batches(session, """UNWIND $rows AS r MATCH (c:Character {id: r.character_id}), (t:Team {id: r.team_id})
                     CREATE (c)-[:MEMBER_OF {role: r.role, status: r.status, source: r.source,
                                             source_url: r.source_url}]->(t)""", data["memberships"])
    for relation, rows in data["facts"].items():  # RELATION names come from a fixed list, not the data
        for (fl, tl) in {(r["from_label"], r["to_label"]) for r in rows}:
            run_batches(session, f"""UNWIND $rows AS r MATCH (a:{fl} {{{KEYS[fl]}: r.from}}), (b:{tl} {{{KEYS[tl]}: r.to}})
                              CREATE (a)-[:{relation} {{title_qid: r.title_qid, episode: r.episode,
                                  evidence: r.evidence, note: r.note, chunk: r.chunk, source: 'plot'}}]->(b)""",
                 [r for r in rows if (r["from_label"], r["to_label"]) == (fl, tl)])


def read_data():
    registry = read_csv(REGISTRY_PATH)
    teams = [{"id": t["team_id"], "name": t["name"], "reality": t["reality"], "kind": t["kind"],
              "aliases": _split(t["aliases"])} for t in read_csv(TEAMS_PATH)]
    characters = character_rows(read_csv(CHARACTERS_PATH), read_csv(ALIASES_PATH))
    people, plays, appears, acted_in = performance_rows(read_csv(PERFORMANCES_PATH))
    details = read_csv(TITLE_DETAILS_PATH)
    crew = crew_rows(details, people)
    birth_dates(people, read_csv(ACTOR_BIRTHS_PATH), read_csv(TMDB_BIRTHDAYS_PATH))
    outputs = {p.stem: read_json(p) for p in sorted(OUTPUTS_DIR.glob("*.json"))}
    things, facts = fact_rows(outputs, {t["wikidata_qid"]: t["reality"] for t in registry}, {t["id"] for t in teams},
                              name_index(teams, "name"), name_index(characters, "label"))
    return {
        "titles": title_rows(registry, _by_qid(RELEASE_ORDER_PATH), _by_qid(TITLE_PHASES_PATH), _by_qid(TIMELINE_PATH),
                             _by_qid(WIKIDATA_MONEY_PATH), _by_qid(TMDB_STATS_PATH)),
        "characters": characters,
        "people": list(people.values()), "plays": plays, "appears": appears, "acted_in": acted_in,
        "crew": crew, "follows": follows_rows(details),
        "teams": teams,
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
