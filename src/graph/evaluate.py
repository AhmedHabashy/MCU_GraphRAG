"""Run the 50 evaluation questions (docs/evaluation_questions.md) against the loaded graph.

Each question is a Cypher query plus the key items of its expected answer. Statuses:
  PASS          the graph gives the expected answer
  PARTIAL       part of it (missing or extra items are shown)
  FAIL          the graph gives a wrong or no answer
  NOT IN GRAPH  the answer needs data that is collected but not loaded (directors, money, years...)
  FACTS FOUND / FACTS MISSING   plot-text questions: whether the facts the answer rests on are in
                the graph (writing the answer itself is the chatbot's job)

Run:  .venv\\Scripts\\python.exe -m src.graph.evaluate
"""

from src.graph.neo4j_db import connect
from src.source_data_collection.cast_matching import normalize_name

QUESTIONS = {}


def question(qid, source="data"):
    def register(fn):
        QUESTIONS[qid] = (source, fn)
        return fn
    return register


def compare(found, expected, exact=True):
    """PASS / PARTIAL / FAIL for two sets of names (normalized), with what differs."""
    f, e = {normalize_name(x) for x in found}, {normalize_name(x) for x in expected}
    missing, extra = e - f, (f - e if exact else set())
    status = "PASS" if not missing and not extra else ("PARTIAL" if f & e else "FAIL")
    detail = []
    if missing:
        detail.append(f"missing {sorted(missing)}")
    if extra:
        detail.append(f"extra {sorted(extra)[:12]}{' ...' if len(extra) > 12 else ''}")
    return status, "; ".join(detail) or f"{len(f)} items"


def named(rows, expected, key="names"):
    """Expected names matched against each row's label and aliases: (found expected names, unmatched rows)."""
    wanted = {normalize_name(e): e for e in expected}
    found, unmatched = set(), []
    for r in rows:
        hits = {wanted[n] for n in map(normalize_name, r[key]) if n in wanted}
        found |= hits
        if not hits:
            unmatched.append(r[key][0])
    return found, unmatched


def compare_named(rows, expected, exact=True):
    found, unmatched = named(rows, expected)
    status, detail = compare(found, expected, exact=False)
    if exact and unmatched:
        status = "PARTIAL" if found else "FAIL"
        detail = "; ".join(x for x in (detail if detail != f"{len(found)} items" else "",
                                       f"extra {sorted(unmatched)[:12]}") if x)
    return status, detail or f"{len(found)} items"


def facts(db, cypher, **params):
    rows = db(cypher, **params)
    return ("FACTS FOUND" if rows else "FACTS MISSING"), "; ".join(
        f"{r['fact']}" for r in rows[:4]) or "none"


NAMES = "[c.label] + c.aliases AS names"


# --- Multi-hop ------------------------------------------------------------------------------

@question("Q01")
def q01(db):
    rows = db("""MATCH (a:Actor)-[:PLAYS {title_qid: 'Q113244839'}]->(c:Character)-[:APPEARS_IN]->(:Title {universe: 'Fox X-Men'})
                 RETURN DISTINCT a.name AS name""")
    return compare([r["name"] for r in rows], ["Patrick Stewart", "Ian McKellen", "James Marsden", "Kelsey Grammer",
                                               "Alan Cumming", "Rebecca Romijn"])


@question("Q02")
def q02(db):
    rows = db("""MATCH (a:Actor)-[:PLAYS]->(c:Character)-[:APPEARS_IN]->(t:Title)
                 WITH a, c, count(DISTINCT t) AS n
                 WITH a, collect(DISTINCT c.base_qid) AS bases, collect(c) AS cs
                 WHERE size(bases) >= 2
                   AND NOT EXISTS { MATCH (x:Character)-[:VARIANT_OF]-(y:Character)
                                    WHERE x IN cs AND y IN cs AND x.base_qid <> y.base_qid
                                    AND size(bases) = 2 }
                 RETURN a.name AS name""")
    expected = ["Chris Evans", "Robert Downey Jr.", "Josh Brolin", "Oscar Isaac", "Paul Bettany", "Peter Dinklage",
                "Michael B. Jordan", "Aaron Taylor-Johnson", "Laurence Fishburne"]
    status, detail = compare([r["name"] for r in rows], expected, exact=False)
    # "Major" needs billing order, which is not loaded: the graph lists every actor with two characters.
    return ("PARTIAL" if status == "PASS" and len(rows) > len(expected) else status),         f"{detail} among {len(rows)} actors with two or more characters ('major' needs billing order, not loaded)"


@question("Q03")
def q03(db):
    rows = db("""MATCH (c:Character {base_qid: 'Q24022542'})-[:APPEARS_IN]->(t:Title)
                 OPTIONAL MATCH (a:Actor)-[:PLAYS]->(c) RETURN DISTINCT t.title AS title, a.name AS actor""")
    status, detail = compare({r["title"] for r in rows}, [
        "Captain America: The Winter Soldier", "Avengers: Age of Ultron", "Captain America: Civil War",
        "Avengers: Infinity War", "Avengers: Endgame", "WandaVision", "Doctor Strange in the Multiverse of Madness",
        "VisionQuest", "What If...?", "Marvel Zombies"])
    actors = {r["actor"] for r in rows if r["actor"]}
    return (status if actors == {"Elizabeth Olsen"} else "PARTIAL"), f"{detail}; actors {sorted(actors)}"


@question("Q04")
def q04(db):
    rows = db("""MATCH (a:Actor)-[:PLAYS {title_qid: 'Q68934496'}]->(c:Character)
                 WHERE c.reality <> 'Earth-616' RETURN DISTINCT a.name AS name""")
    return compare([r["name"] for r in rows], ["Tobey Maguire", "Willem Dafoe", "Alfred Molina", "Thomas Haden Church",
                                               "Andrew Garfield", "Jamie Foxx", "Rhys Ifans", "Tom Hardy"])


@question("Q05")
def q05(db):
    rows = db("""MATCH (a:Actor)-[:PLAYS {title_qid: 'Q16977365'}]->(:Character)
                 MATCH (a)-[p:PLAYS]->(:Character) WHERE p.title_qid <> 'Q16977365'
                 RETURN DISTINCT a.name AS name""")
    return compare([r["name"] for r in rows], [
        "Charlie Cox", "Vincent D'Onofrio", "Jon Bernthal", "Deborah Ann Woll", "Elden Henson", "Rosario Dawson",
        "Élodie Yung", "Stephen Rider", "Ayelet Zurer", "Wilson Bethel", "Toby Leonard Moore"])


@question("Q06")
def q06(db):
    rows = db("""MATCH (:Actor {name: 'Jonathan Majors'})-[:PLAYS]->(c:Character)
                 OPTIONAL MATCH (c)-[:VARIANT_OF]-(k:Character {base_qid: 'Q1982051'})
                 RETURN DISTINCT c.label AS label, c.base_qid = 'Q1982051' OR k IS NOT NULL AS kang""")
    status, detail = compare({r["label"] for r in rows}, ["He Who Remains", "Victor Timely", "Kang the Conqueror"])
    not_linked = [r["label"] for r in rows if not r["kang"]]
    return (status if not not_linked else "PARTIAL"), detail + (f"; not linked to Kang: {not_linked}" if not_linked else "")


@question("Q07")
def q07(db):
    rows = db(f"""MATCH (:Title {{qid: 'Q113244839'}})<-[:APPEARS_IN]-(c:Character)-[:APPEARS_IN]->(:Title {{qid: 'Q23781155'}})
                  RETURN {NAMES}""")
    return compare_named(rows, ["Steve Rogers", "Thor", "Loki", "Sam Wilson", "Bucky Barnes", "Scott Lang",
                                "Cassie Lang", "Shuri", "M'Baku", "Peggy Carter"])


@question("Q08")
def q08(db):
    return "NOT IN GRAPH", "directors are collected (title_details) but not loaded"


@question("Q09")
def q09(db):
    rows = db("""MATCH (:Actor {name: 'Hugh Jackman'})-[:PLAYS]->(c:Character) RETURN DISTINCT c.id AS id""")
    return compare([r["id"] for r in rows], ["Q97275436@Earth-10005", "Q97275436@Earth-17315",
                                             "mcuwiki:Wolverine@Unknown", "Q50805198@Earth-17315"])


@question("Q10")
def q10(db):
    rows = db("""MATCH (a:Actor)-[:PLAYS]->(c:Character {base_qid: 'Q23894967'}) RETURN DISTINCT a.name AS name, c.reality AS reality""")
    return compare({f"{r['name']} {r['reality']}" for r in rows}, [
        "Robert Downey Jr. Earth-616", "Mick Wingert Multiverse", "Mick Wingert Earth-86445"])


# --- Timeline -------------------------------------------------------------------------------

@question("Q11")
def q11(db):
    rows = db("MATCH (t:Title) WHERE t.chronological_order IS NOT NULL RETURN t.title AS title ORDER BY t.chronological_order LIMIT 1")
    status, detail = compare([r["title"] for r in rows], ["Eyes of Wakanda"])
    return ("PARTIAL" if status == "PASS" else status), detail + "; the in-universe years are not loaded"


@question("Q12")
def q12(db):
    return "NOT IN GRAPH", "in-universe years are collected (timeline) but not loaded"


@question("Q13")
def q13(db):
    rows = db("""MATCH (e:Title {qid: 'Q23781155'}), (t:Title)
                 WHERE t.release_order > e.release_order AND t.chronological_order < e.chronological_order
                 RETURN t.title AS title""")
    return compare([r["title"] for r in rows], ["Black Widow", "I Am Groot", "Eyes of Wakanda"], exact=False)


@question("Q14")
def q14(db):
    rows = db("""MATCH (t:Title) WHERE 'Phase One' IN t.phases RETURN t.title AS title ORDER BY t.chronological_order""")
    order = [r["title"] for r in rows]
    expected = ["Captain America: The First Avenger", "Iron Man", "Iron Man 2", "Thor", "The Incredible Hulk", "The Avengers"]
    return ("PASS" if order == expected else "FAIL"), " > ".join(order)


@question("Q15")
def q15(db):
    return "NOT IN GRAPH", "in-universe years are collected (timeline) but not loaded"


@question("Q16", "plot text")
def q16(db):
    return facts(db, """MATCH (c:Character {label: 'Thanos'})-[r]->(o) WHERE r.title_qid = 'Q23780914'
                        RETURN type(r) + ' ' + coalesce(o.label, o.name) + ': ' + r.evidence AS fact""")


@question("Q17", "plot text")
def q17(db):
    return facts(db, """MATCH (a)-[r]->(o) WHERE r.title_qid = 'Q23781155'
                          AND (coalesce(o.name, '') CONTAINS 'Quantum' OR coalesce(o.name, '') CONTAINS 'Stone'
                               OR (a.label = 'Tony Stark' AND type(r) = 'KILLS'))
                        RETURN coalesce(a.label, a.name) + ' ' + type(r) + ' ' + coalesce(o.label, o.name) AS fact""")


@question("Q18", "plot text")
def q18(db):
    return facts(db, """MATCH (a)-[r:KILLS]->(o:Character {label: 'He Who Remains'})
                        RETURN coalesce(a.label, a.name) + ' KILLS He Who Remains (' + r.title_qid + ')' AS fact""")


# --- Identity -------------------------------------------------------------------------------

@question("Q19")
def q19(db):
    rows = db("""MATCH (s:Character {id: 'Q107723311@Earth-616'}), (l:Character {id: 'Q24046118@Earth-616'})
                 RETURN s <> l AS separate, EXISTS { (s)-[:VARIANT_OF]-(l) } AS variant""")
    r = rows[0]
    return ("PASS" if r["separate"] and r["variant"] else "PARTIAL" if r["separate"] else "FAIL"), \
        f"separate nodes: {r['separate']}; linked as variants: {r['variant']}"


@question("Q20")
def q20(db):
    rows = db("""MATCH (w:Character {id: 'Q97275436@Earth-10005'})-[:VARIANT_OF*1..2]-(v:Character)
                 RETURN DISTINCT v.id AS id""")
    return compare({r["id"] for r in rows} | {"Q97275436@Earth-10005"}, [
        "Q97275436@Earth-10005", "Q97275436@Earth-17315", "Q186422@Earth-92131", "mcuwiki:Wolverine@Unknown",
        "mcuwiki:Cavillrine@Unknown", "Q50805198@Earth-17315"], exact=False)


@question("Q21", "expert")
def q21(db):
    rows = db("""MATCH (a:Actor {name: 'Hayley Atwell'})-[:PLAYS]->(c:Character {base_qid: 'Q24034679'})
                 RETURN collect(DISTINCT c.id) AS ids""")
    return compare(rows[0]["ids"], ["Q24034679@Earth-616", "Q24034679@Earth-838", "Q24034679@Multiverse"])


@question("Q22", "expert")
def q22(db):
    rows = db("""MATCH (a:Actor)-[p:PLAYS]->(c:Character) WHERE p.title_qid IN ['Q113244839', 'Q64211112']
                   AND (c.label = 'Reed Richards' OR 'Mister Fantastic' IN c.aliases)
                 RETURN DISTINCT a.name + ' ' + c.reality AS r""")
    return compare([r["r"] for r in rows], ["Pedro Pascal Earth-828", "John Krasinski Earth-838"])


@question("Q23", "expert")
def q23(db):
    rows = db("""MATCH (c:Character {id: 'Q302186@Earth-10005'})-[:APPEARS_IN]->(t:Title) RETURN t.title AS title""")
    status, detail = compare([r["title"] for r in rows], ["The Marvels", "Avengers: Doomsday"], exact=False)
    variant = db("MATCH (:Character {id: 'Q302186@Earth-10005'})-[:VARIANT_OF]-(v:Character {id: 'Q302186@Earth-92131'}) RETURN v")
    return (status if variant else "PARTIAL"), detail + f"; X-Men '97 Beast linked as variant: {bool(variant)}"


@question("Q24")
def q24(db):
    rows = db("MATCH (c:Character {id: 'Q24022542@Earth-616'}) RETURN c.aliases AS aliases")
    return compare(rows[0]["aliases"], ["Scarlet Witch", "Glamour", "Harbinger of Chaos"], exact=False)


@question("Q25", "expert")
def q25(db):
    rows = db("""MATCH (a:Actor)-[:PLAYS]->(c:Character) WHERE c.label = 'Johnny Storm'
                 RETURN DISTINCT a.name + ' ' + c.reality AS r""")
    return compare([r["r"] for r in rows], ["Chris Evans Earth-121698", "Joseph Quinn Earth-828",
                                            "Michael B. Jordan Earth-15866"])


@question("Q26", "expert")
def q26(db):
    rows = db("""MATCH (c:Character {label: 'Gambit'})-[:APPEARS_IN]->(t:Title)
                 WHERE t.qid IN ['Q113244839', 'Q102180106'] RETURN c.id AS id, collect(t.title) AS titles""")
    one = [r for r in rows if len(r["titles"]) == 2]
    return ("PASS" if one and one[0]["id"] == "Q2639150@Unknown" else "FAIL"), str([(r["id"], r["titles"]) for r in rows])


@question("Q27", "expert")
def q27(db):
    rows = db("""MATCH (a:Actor)-[:PLAYS]->(c:Character {id: 'Q23991271@Earth-616'}) RETURN c.aliases AS aliases, collect(DISTINCT a.name) AS actors""")
    may = any("maybelle" in normalize_name(a) for a in rows[0]["aliases"])
    tomei = "Marisa Tomei" in rows[0]["actors"]
    return ("PASS" if may and tomei else "PARTIAL" if may or tomei else "FAIL"), f"Maybelle alias: {may}; Marisa Tomei: {tomei}"


# --- Teams ----------------------------------------------------------------------------------

def members(db, team, where="m.source <> 'plot'"):
    return db(f"MATCH (c:Character)-[m:MEMBER_OF]->(:Team {{id: $team}}) WHERE {where} RETURN DISTINCT {NAMES}", team=team)


@question("Q28")
def q28(db):
    return compare_named(members(db, "Illuminati@Earth-838"), [
        "Professor X", "Captain Carter", "Maria Rambeau", "Black Bolt", "Reed Richards", "Baron Mordo", "Stephen Strange"])


@question("Q29")
def q29(db):
    rows = db(f"""MATCH (c:Character)-[m1:MEMBER_OF]->(:Team {{id: 'Avengers@Earth-616'}}),
                        (c)-[m2:MEMBER_OF]->(:Team {{id: 'Guardians of the Galaxy@Earth-616'}})
                  WHERE m1.source <> 'plot' AND m2.source <> 'plot' RETURN DISTINCT {NAMES}""")
    return compare_named(rows, ["Thor", "Nebula", "Rocket"])


@question("Q30")
def q30(db):
    return compare_named(members(db, "New Avengers@Earth-616"), [
        "Yelena Belova", "Bucky Barnes", "Alexei Shostakov", "Ava Starr", "John Walker", "Sentry",
        "Valentina Allegra de Fontaine"], exact=False)


@question("Q31")
def q31(db):
    rows = db(f"""MATCH (c:Character)-[m:MEMBER_OF {{role: 'leader'}}]->(:Team {{id: 'Avengers@Earth-616'}})
                  WHERE m.source <> 'plot' RETURN DISTINCT {NAMES}, m.status AS status""")
    current = [r for r in rows if r["status"] == "current"]
    status, detail = compare_named(rows, ["Sam Wilson", "Nick Fury", "Steve Rogers", "Tony Stark", "Natasha Romanoff"], exact=False)
    now, _ = named(current, ["Sam Wilson"])
    return (status if now else "PARTIAL"), detail + f"; current leader Sam Wilson: {bool(now)}"


@question("Q32")
def q32(db):
    rows = db(f"""MATCH (c:Character)-[m:MEMBER_OF]->(:Team {{id: 'Fantastic Four@Earth-828'}})
                  WHERE m.source <> 'plot' AND (c)-[:APPEARS_IN]->(:Title {{qid: 'Q113244839'}}) RETURN DISTINCT {NAMES}""")
    return compare_named(rows, ["Reed Richards", "Sue Storm", "Johnny Storm", "Ben Grimm"])


@question("Q33")
def q33(db):
    rows = db(f"""MATCH (c:Character)-[m:MEMBER_OF]->(:Team {{id: 'X-Men@Earth-10005'}})
                  WHERE m.source <> 'plot' AND (c)-[:APPEARS_IN]->(:Title {{qid: 'Q113244839'}}) RETURN DISTINCT {NAMES}""")
    return compare_named(rows, ["Charles Xavier", "Cyclops", "Beast", "Nightcrawler", "Magneto", "Mystique"])


@question("Q34", "expert")
def q34(db):
    return facts(db, """MATCH (a)-[r]->(o) WHERE r.title_qid = 'Q29226331' AND type(r) IN ['LEADS', 'MEMBER_OF', 'CREATES']
                        RETURN coalesce(a.label, a.name) + ' ' + type(r) + ' ' + coalesce(o.label, o.name) AS fact""")


# --- Big picture ----------------------------------------------------------------------------

@question("Q35")
def q35(db):
    rows = db("MATCH (t:Title) WHERE 'Phase Four' IN t.phases RETURN t.title AS title")
    return compare([r["title"] for r in rows], [
        "WandaVision", "The Falcon and the Winter Soldier", "Loki, season 1", "What If...?", "Black Widow",
        "Shang-Chi and the Legend of the Ten Rings", "Eternals", "Hawkeye", "Spider-Man: No Way Home", "Moon Knight",
        "Doctor Strange in the Multiverse of Madness", "Ms. Marvel", "Thor: Love and Thunder", "I Am Groot",
        "She-Hulk: Attorney at Law", "Werewolf by Night", "Black Panther: Wakanda Forever",
        "The Guardians of the Galaxy Holiday Special"])


@question("Q36", "plot text")
def q36(db):
    n = db("MATCH (t:Title {type: 'Film'}) WHERE 'The Infinity Saga' IN t.sagas RETURN count(t) AS n")[0]["n"]
    status, detail = facts(db, """MATCH (a:Character {label: 'Thanos'})-[r:POSSESSES]->(o)
                                  RETURN 'Thanos POSSESSES ' + o.name AS fact""")
    return status, f"{n} Infinity Saga films (expected 23); {detail}"


@question("Q37")
def q37(db):
    r = db("MATCH (t:Title {qid: 'Q113244839'}) RETURN t.phases AS p, t.sagas AS s")[0]
    return ("PASS" if r["p"] == ["Phase Six"] and r["s"] == ["The Multiverse Saga"] else "FAIL"), f"{r['p']} {r['s']}"


@question("Q38")
def q38(db):
    rows = db("MATCH (t:Title) UNWIND t.phases AS p RETURN p, count(t) AS n")
    found = {f"{r['p']} {r['n']}" for r in rows}
    return compare(found, ["Phase One 6", "Phase Two 6", "Phase Three 11", "Phase Four 18", "Phase Five 15", "Phase Six 9"])


@question("Q39")
def q39(db):
    n = db("MATCH (t:Title) WHERE size(t.phases) = 0 RETURN count(t) AS n")[0]["n"]
    return ("PASS" if n == 37 else "FAIL"), f"{n} titles (expected 37)"


@question("Q40", "plot text")
def q40(db):
    return facts(db, """MATCH (a:Actor {name: 'Robert Downey Jr.'})-[:PLAYS {title_qid: 'Q113244839'}]->(c:Character)
                        RETURN 'Robert Downey Jr. plays ' + c.label + ' in Avengers: Doomsday' AS fact
                        UNION MATCH (v:Character)-[:VARIANT_OF]-(:Character {base_qid: 'Q1982051'})
                        RETURN v.label + ' is a Kang variant' AS fact""")


# --- Analytics ------------------------------------------------------------------------------

for _qid, _what in (("Q41", "box office"), ("Q42", "box office"), ("Q43", "box office and sequel links"),
                    ("Q47", "budgets"), ("Q48", "TMDB ratings"), ("Q49", "actor birth dates and release dates"),
                    ("Q50", "TMDB ratings")):
    QUESTIONS[_qid] = ("data", lambda db, w=_what: ("NOT IN GRAPH", f"{w} collected (title_stats, title_details) but not loaded"))


CAMEO = "Watcher Informant"


@question("Q44")
def q44(db):
    rows = db("""MATCH (c:Character)-[:APPEARS_IN]->(t:Title) WHERE c.label <> $cameo
                 RETURN c.id AS id, c.label AS label, count(DISTINCT t) AS n ORDER BY n DESC LIMIT 2""", cameo=CAMEO)
    top = [f"{r['label']} {r['n']}" for r in rows]
    return ("PASS" if top == ["Nick Fury 14", "Steve Rogers 12"] else "FAIL"), ", ".join(top)


@question("Q45")
def q45(db):
    rows = db("""MATCH (a:Actor)-[p:PLAYS]->() RETURN a.name AS name, count(DISTINCT p.title_qid) AS n ORDER BY n DESC LIMIT 3""")
    top = [f"{r['name']} {r['n']}" for r in rows]
    return ("PASS" if top[0] == "Stan Lee 36" and set(top[1:]) == {"Samuel L. Jackson 15", "Chris Evans 15"} else "FAIL"), ", ".join(top)


@question("Q46")
def q46(db):
    rows = db("""MATCH (c:Character)-[:APPEARS_IN]->(t:Title {type: 'Film'})<-[:APPEARS_IN]-(o:Character)
                 WHERE c <> o AND c.label <> $cameo
                 RETURN c.id AS id, c.label AS label, count(DISTINCT o) AS n ORDER BY n DESC LIMIT 3""", cameo=CAMEO)
    top = [f"{r['label']} {r['n']}" for r in rows]
    return ("PASS" if top == ["Steve Rogers 239", "Nick Fury 223", "Thor 201"] else "FAIL"), ", ".join(top)


def main():
    counts = {}
    with connect() as driver:
        db = lambda cypher, **params: driver.execute_query(cypher, **params).records
        for qid in sorted(QUESTIONS):
            source, fn = QUESTIONS[qid]
            status, detail = fn(db)
            counts[status] = counts.get(status, 0) + 1
            print(f"{qid} [{source}] {status}: {detail}")
    print(" | ".join(f"{k} {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
