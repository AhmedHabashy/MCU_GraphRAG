"""Run the 50 evaluation questions (docs/evaluation_questions.md) against the loaded graph.

Each question is a Cypher query plus the key items of its expected answer. Statuses:
  PASS          the graph gives the expected answer
  PARTIAL       part of it (missing or extra items are shown)
  FAIL          the graph gives a wrong or no answer
  NOT IN GRAPH  the answer needs data that is collected but not loaded
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
    rows = db("""MATCH (a:Person)-[:PLAYS {title_qid: 'Q113244839'}]->(c:Character)-[:APPEARS_IN]->(:Title {universe: 'Fox X-Men'})
                 RETURN DISTINCT a.name AS name""")
    return compare([r["name"] for r in rows], ["Patrick Stewart", "Ian McKellen", "James Marsden", "Kelsey Grammer",
                                               "Alan Cumming", "Rebecca Romijn"])


@question("Q02")
def q02(db):
    # "Major" is taken as billed in the top 10 of some title; the expected list is a judgement, so
    # extras such as Gemma Chan (Minn-Erva, Sersi) are shown, not counted as wrong.
    rows = db("""MATCH (a:Person)-[p:PLAYS]->(c:Character) WHERE p.billing_order < 10
                 WITH a, collect(DISTINCT c.base_qid) AS bases WHERE size(bases) >= 2
                 RETURN a.name AS name""")
    expected = ["Chris Evans", "Robert Downey Jr.", "Josh Brolin", "Oscar Isaac", "Paul Bettany", "Peter Dinklage",
                "Michael B. Jordan", "Aaron Taylor-Johnson", "Laurence Fishburne"]
    status, detail = compare([r["name"] for r in rows], expected)
    return ("PARTIAL" if status == "PASS" else status), f"top-10 billing: {detail}"


@question("Q03")
def q03(db):
    rows = db("""MATCH (c:Character {base_qid: 'Q24022542'})-[:APPEARS_IN]->(t:Title)
                 OPTIONAL MATCH (a:Person)-[:PLAYS]->(c) RETURN DISTINCT t.title AS title, a.name AS actor""")
    status, detail = compare({r["title"] for r in rows}, [
        "Captain America: The Winter Soldier", "Avengers: Age of Ultron", "Captain America: Civil War",
        "Avengers: Infinity War", "Avengers: Endgame", "WandaVision", "Doctor Strange in the Multiverse of Madness",
        "VisionQuest", "What If...?", "Marvel Zombies"])
    actors = {r["actor"] for r in rows if r["actor"]}
    return (status if actors == {"Elizabeth Olsen"} else "PARTIAL"), f"{detail}; actors {sorted(actors)}"


@question("Q04")
def q04(db):
    rows = db("""MATCH (a:Person)-[:PLAYS {title_qid: 'Q68934496'}]->(c:Character)
                 WHERE c.reality <> 'Earth-616' RETURN DISTINCT a.name AS name""")
    return compare([r["name"] for r in rows], ["Tobey Maguire", "Willem Dafoe", "Alfred Molina", "Thomas Haden Church",
                                               "Andrew Garfield", "Jamie Foxx", "Rhys Ifans", "Tom Hardy"])


@question("Q05")
def q05(db):
    rows = db("""MATCH (a:Person)-[:PLAYS {title_qid: 'Q16977365'}]->(:Character)
                 MATCH (a)-[p:PLAYS]->(:Character) WHERE p.title_qid <> 'Q16977365'
                 RETURN DISTINCT a.name AS name""")
    return compare([r["name"] for r in rows], [
        "Charlie Cox", "Vincent D'Onofrio", "Jon Bernthal", "Deborah Ann Woll", "Elden Henson", "Rosario Dawson",
        "Élodie Yung", "Stephen Rider", "Ayelet Zurer", "Wilson Bethel", "Toby Leonard Moore"])


@question("Q06")
def q06(db):
    rows = db("""MATCH (:Person {name: 'Jonathan Majors'})-[:PLAYS]->(c:Character)
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
    rows = db("""MATCH (p:Person)-[:DIRECTED]->(t:Title {type: 'Film'})
                 RETURN p.name AS name, count(t) AS n ORDER BY n DESC, name LIMIT 4""")
    return compare({f"{r['name']} {r['n']}" for r in rows},
                   ["Anthony Russo 5", "Joe Russo 5", "Bryan Singer 4", "Sam Raimi 4"])


@question("Q09")
def q09(db):
    rows = db("""MATCH (:Person {name: 'Hugh Jackman'})-[:PLAYS]->(c:Character) RETURN DISTINCT c.id AS id""")
    return compare([r["id"] for r in rows], ["Q97275436@Earth-10005", "Q97275436@Earth-17315",
                                             "mcuwiki:Wolverine@Unknown", "Q50805198@Earth-17315"])


@question("Q10")
def q10(db):
    rows = db("""MATCH (a:Person)-[:PLAYS]->(c:Character {base_qid: 'Q23894967'}) RETURN DISTINCT a.name AS name, c.reality AS reality""")
    return compare({f"{r['name']} {r['reality']}" for r in rows}, [
        "Robert Downey Jr. Earth-616", "Mick Wingert Multiverse", "Mick Wingert Earth-86445"])


# --- Timeline -------------------------------------------------------------------------------

@question("Q11")
def q11(db):
    first = db("""MATCH (t:Title) WHERE t.start_year IS NOT NULL
                  RETURN t.title AS title, t.start_year AS y ORDER BY t.start_year LIMIT 1""")[0]
    film = db("""MATCH (t:Title {type: 'Film', universe: 'MCU'}) WHERE t.start_year IS NOT NULL
                 RETURN t.title AS title, t.start_year AS s, t.end_year AS e ORDER BY t.start_year LIMIT 1""")[0]
    got = (first["title"], first["y"], film["title"], film["s"], film["e"])
    expected = ("Eyes of Wakanda", -1260, "Captain America: The First Avenger", 1942, 1945)
    return ("PASS" if got == expected else "FAIL"), str(got)


@question("Q12")
def q12(db):
    r = db("MATCH (t:Title {title: 'Captain Marvel'}) RETURN t.start_year AS s, t.end_year AS e")[0]
    return ("PASS" if (r["s"], r["e"]) == (1995, 1995) else "FAIL"), f"{r['s']}-{r['e']}"


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
    r = db("MATCH (t:Title {qid: 'Q23781155'}) RETURN t.start_year AS s, t.end_year AS e")[0]
    return ("PASS" if (r["s"], r["e"]) == (2018, 2023) else "FAIL"), f"Endgame {r['s']}-{r['e']}: {r['e'] - r['s']} years"


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
    rows = db("""MATCH (a:Person {name: 'Hayley Atwell'})-[:PLAYS]->(c:Character {base_qid: 'Q24034679'})
                 RETURN collect(DISTINCT c.id) AS ids""")
    return compare(rows[0]["ids"], ["Q24034679@Earth-616", "Q24034679@Earth-838", "Q24034679@Multiverse"])


@question("Q22", "expert")
def q22(db):
    rows = db("""MATCH (a:Person)-[p:PLAYS]->(c:Character) WHERE p.title_qid IN ['Q113244839', 'Q64211112']
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
    rows = db("""MATCH (a:Person)-[:PLAYS]->(c:Character) WHERE c.label = 'Johnny Storm'
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
    rows = db("""MATCH (a:Person)-[:PLAYS]->(c:Character {id: 'Q23991271@Earth-616'}) RETURN c.aliases AS aliases, collect(DISTINCT a.name) AS actors""")
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
    return facts(db, """MATCH (a:Person {name: 'Robert Downey Jr.'})-[:PLAYS {title_qid: 'Q113244839'}]->(c:Character)
                        RETURN 'Robert Downey Jr. plays ' + c.label + ' in Avengers: Doomsday' AS fact
                        UNION MATCH (v:Character)-[:VARIANT_OF]-(:Character {base_qid: 'Q1982051'})
                        RETURN v.label + ' is a Kang variant' AS fact""")


# --- Analytics ------------------------------------------------------------------------------

@question("Q41")
def q41(db):
    r = db("MATCH (t:Title) WHERE t.box_office_usd IS NOT NULL RETURN t.title AS t, t.box_office_usd AS b ORDER BY b DESC LIMIT 1")[0]
    return ("PASS" if r["t"] == "Avengers: Endgame" and round(r["b"] / 1e9, 2) == 2.80 else "FAIL"), f"{r['t']} ${r['b']:,}"


@question("Q42")
def q42(db):
    least = "MATCH (t:Title {type: 'Film'}) WHERE t.box_office_usd IS NOT NULL FILTER RETURN t.title AS t, t.box_office_usd AS b ORDER BY b LIMIT 1"
    mcu, every = db(least.replace("FILTER", "AND t.universe = 'MCU'"))[0], db(least.replace("FILTER", ""))[0]
    got = (mcu["t"], round(mcu["b"] / 1e6), every["t"], round(every["b"] / 1e6))
    ok = mcu["t"] == "The Marvels" and every["t"] == "The New Mutants"
    return ("PASS" if ok else "FAIL"), f"MCU: {mcu['t']} ${got[1]}M; all: {every['t']} ${got[3]}M"


@question("Q43")
def q43(db):
    rows = db("""MATCH (s:Title {type: 'Film'})-[:FOLLOWS]->(p:Title {type: 'Film'})
                 WHERE s.box_office_usd IS NOT NULL AND p.box_office_usd IS NOT NULL
                 RETURN s.title AS sequel, s.box_office_usd > p.box_office_usd AS more""")
    less = [r["sequel"] for r in rows if not r["more"]]
    status, detail = compare(set(less), [
        "Avengers: Age of Ultron", "Thor: Love and Thunder", "Guardians of the Galaxy Vol. 3",
        "Ant-Man and the Wasp: Quantumania", "Black Panther: Wakanda Forever", "The Marvels",
        "Captain America: Brave New World", "X-Men: Apocalypse", "Dark Phoenix",
        "Fantastic Four: Rise of the Silver Surfer", "Spider-Man 2", "The Amazing Spider-Man 2",
        "Venom: Let There Be Carnage", "Venom: The Last Dance"])
    return status, f"{len(rows) - len(less)} of {len(rows)} sequels earned more; {detail}"


@question("Q47")
def q47(db):
    r = db("MATCH (t:Title {type: 'Film'}) WHERE t.budget_usd IS NOT NULL RETURN t.title AS t, t.budget_usd AS b ORDER BY b DESC LIMIT 1")[0]
    return ("PASS" if (r["t"], r["b"]) == ("Avengers: Infinity War", 400_000_000) else "FAIL"), f"{r['t']} ${r['b']:,}"


@question("Q48")
def q48(db):
    rows = db("""MATCH (t:Title {type: 'Film'}) WHERE t.tmdb_rating > 0
                 UNWIND (CASE WHEN size(t.phases) = 0 THEN ['outside the phases'] ELSE t.phases END) AS phase
                 RETURN phase, round(avg(t.tmdb_rating), 2) AS avg""")
    return compare({f"{r['phase']} {r['avg']:.2f}" for r in rows}, [
        "Phase One 7.12", "Phase Two 7.22", "Phase Three 7.48", "Phase Four 7.12", "Phase Five 6.81",
        "Phase Six 7.69", "outside the phases 6.58"])


@question("Q49")
def q49(db):
    r = db("""MATCH (p:Person {name: 'Robert Downey Jr.'}), (t:Title {title: 'Iron Man'})
              RETURN p.birth_date AS b, t.first_release_date AS d""")[0]
    b, d = r["b"], r["d"]
    age = int(d[:4]) - int(b[:4]) - ((d[5:] < b[5:]) if b and d else 0)
    return ("PASS" if age == 43 else "FAIL"), f"born {b}, Iron Man first released {d}: {age}"


@question("Q50")
def q50(db):
    top = db("MATCH (t:Title) WHERE t.tmdb_rating IS NOT NULL RETURN t.title AS t, t.tmdb_rating AS r ORDER BY r DESC LIMIT 1")[0]
    films = db("MATCH (t:Title {type: 'Film'}) WHERE t.tmdb_rating IS NOT NULL RETURN t.title AS t, t.tmdb_rating AS r ORDER BY r DESC LIMIT 3")
    got = (top["t"], films[0]["t"], {f["t"] for f in films[1:]})   # Infinity War and Endgame are tied
    expected = ("X-Men '97", "Spider-Man: Brand New Day", {"Avengers: Infinity War", "Avengers: Endgame"})
    return ("PASS" if got == expected else "FAIL"), f"{top['t']} {top['r']}; films: " + ", ".join(f"{f['t']} {f['r']}" for f in films)


@question("Q44")
def q44(db):
    rows = db("""MATCH (c:Character)-[:APPEARS_IN]->(t:Title) WHERE NOT c.cameo
                 RETURN c.id AS id, c.label AS label, count(DISTINCT t) AS n ORDER BY n DESC LIMIT 2""")
    top = [f"{r['label']} {r['n']}" for r in rows]
    return ("PASS" if top == ["Nick Fury 14", "Steve Rogers 12"] else "FAIL"), ", ".join(top)


@question("Q45")
def q45(db):
    rows = db("""MATCH (a:Person)-[r:ACTED_IN]->(t:Title)
                 RETURN a.name AS name, count(t) AS n, count(CASE WHEN r.cameo THEN t END) AS cameos
                 ORDER BY n DESC, name LIMIT 3""")
    top = [f"{r['name']} {r['n']} ({r['cameos']} cameos)" for r in rows]
    expected = ("Stan Lee 36 (36 cameos)", {"Samuel L. Jackson 15 (0 cameos)", "Chris Evans 15 (0 cameos)"})
    return ("PASS" if (top[0], set(top[1:])) == expected else "FAIL"), ", ".join(top)


@question("Q46")
def q46(db):
    rows = db("""MATCH (c:Character)-[:APPEARS_IN]->(t:Title {type: 'Film'})<-[:APPEARS_IN]-(o:Character)
                 WHERE c <> o AND NOT c.cameo
                 RETURN c.id AS id, c.label AS label, count(DISTINCT o) AS n ORDER BY n DESC LIMIT 3""")
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
