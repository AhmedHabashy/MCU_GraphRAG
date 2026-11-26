"""Inputs for the summaries the subagents write (docs/rag_design.md, "Summaries").

One input file per summary holds exactly what its subagent may use. Summaries come in levels:
  1  title digests (from the plot), main characters (profile + plot facts), teams (members + plot facts)
  2  series, phases and universes, from their title digests
  3  sagas, from their phase summaries; realities spanning several universes, from their universe
     summaries (or, for a universe only partly in the reality, the digests of its titles there)
A title too long for one input gets an input per season, and its digest is built from the
season digests. A universe or reality too big from title digests is built from the level that
covers it (phases, universes). A level 2 or 3 input is built only when every summary below it
exists, so run this again after each level is written. Input files no longer built are removed. A summary is pending when its output is missing or was written from
another input (input_hash). Input files are rewritten only when their content changes.

Needs:  the loaded graph with character profiles (src.graph.load_neo4j, src.graph.profiles),
        source_data/wikipedia/plots/
Output: processed_data/summaries/inputs/<kind>/<id>.json (src.graph.summary_status gives the next actions)
Run:    .venv\\Scripts\\python.exe -m src.graph.summary_inputs
"""

import hashlib
import json
import re

from src.graph import prepare_extraction
from src.graph.neo4j_db import connect
from src.graph.prepare_extraction import PLOTS_DIR, episode_text, write_if_changed
from src.graph.profiles import memberships_text
from src.source_data_collection.storage import read_json
from src.source_data_collection.tier_titles import PROJECT_ROOT

SUMMARIES_DIR = PROJECT_ROOT / "processed_data" / "summaries"
INPUTS_DIR = SUMMARIES_DIR / "inputs"
OUTPUTS_DIR = SUMMARIES_DIR / "outputs"
MAX_INPUT_CHARS = 40_000     # larger inputs are reported, not cut
BATCH_CHARS = 60_000         # input text per subagent
BATCH_ITEMS = 20             # summaries per subagent
MIN_FACTS, MIN_TITLES = 5, 3  # a main character has at least this many plot facts or titles
CITATION = re.compile(r"\[(Q\d+)(?: ep (\d+))?\]")


# --- pure helpers --------------------------------------------------------------------------

def make_input(kind, id_, name, level, sources, text):
    digest = hashlib.sha256(f"{kind}\n{id_}\n{text}".encode("utf-8")).hexdigest()[:16]
    return {"kind": kind, "id": id_, "name": name, "level": level, "sources": sources, "text": text,
            "input_hash": digest}


def is_pending(inp, output):
    return output is None or output.get("input_hash") != inp["input_hash"]


def citations(text):
    """{(title qid, episode number or None)} cited in a text."""
    return {(qid, int(ep) if ep else None) for qid, ep in CITATION.findall(text)}


def title_text(plot):
    """A film's plot under one citation, or each episode summary under its own."""
    episodes = [e for e in plot.get("episodes") or [] if e.get("summary_text")]
    if not episodes:
        return f"{cite(plot['title_qid'])}\n{plot['text']}"
    return "\n\n".join(f"{cite(plot['title_qid'], e['number_overall'])} {episode_text(e)}" for e in episodes)


def cite(title_qid, episode=None):
    return f"[{title_qid} ep {episode}]" if episode else f"[{title_qid}]"


def fact_line(fact):
    note = f" (note: {fact['note']})" if fact["note"] else ""
    return (f"{cite(fact['title_qid'], fact['episode'])} {fact['title']}: {fact['subject']} {fact['relation']} "
            f"{fact['object']}: \"{fact['evidence']}\"{note}")


def is_main_character(facts, titles):
    """At least MIN_FACTS plot facts, or MIN_TITLES titles; and at least one plot fact, since a
    summary without one would only restate the profile, with nothing for its key facts to cite."""
    return facts >= 1 and (facts >= MIN_FACTS or titles >= MIN_TITLES)


def summary_block(kind, id_, output):
    """A lower summary as part of an upper input: its text and its cited key facts."""
    source = cite(id_) if kind == "title" else f"({kind} {id_})"
    lines = [f"## {output['name']} {source}", output["summary"]]
    if output.get("key_facts"):
        lines += ["Key facts:"] + [f"- {k['fact']} {k['cite']}" for k in output["key_facts"]]
    return "\n".join(lines)


def _group(kind, id_, name, level, members, outputs, note=None):
    """The input built from member summaries [(kind, id)], after an optional note, or None while
    one is missing."""
    if any(m not in outputs for m in members):
        return None
    text = "\n\n".join(([note] if note else []) + [summary_block(k, i, outputs[(k, i)]) for k, i in members])
    return make_input(kind, id_, name, level, [i for _, i in members], text)


def group_input(kind, id_, name, level, member_kind, member_ids, outputs):
    return _group(kind, id_, name, level, [(member_kind, m) for m in member_ids], outputs)


def reality_sources(reality, title_reality, title_universe):
    """[(kind, id)]: the summary of each universe wholly in the reality, else its titles there."""
    sources = []
    for universe in sorted({title_universe[t] for t, r in title_reality.items() if r == reality}):
        titles = [t for t, u in title_universe.items() if u == universe]
        if all(title_reality[t] == reality for t in titles):
            sources.append(("universe", universe))
        else:
            sources += [("title", t) for t in sorted(titles) if title_reality[t] == reality]
    return sources


def batches(inputs, max_chars=BATCH_CHARS, max_items=BATCH_ITEMS):
    """Inputs grouped per subagent up to max_chars of text and max_items summaries; an input is
    never split."""
    by_key = {(i["kind"], i["id"]): i for i in inputs}
    groups = prepare_extraction.batches([((i["kind"], i["id"]), len(i["text"])) for i in inputs], max_chars)
    return [[by_key[k] for k in group[start:start + max_items]] for group in groups
            for start in range(0, len(group), max_items)]


def file_name(id_):
    return re.sub(r"[^\w@.\- ]", "_", id_) + ".json"


# --- reading the graph ---------------------------------------------------------------------

PLOT_FACTS = """COLLECT { MATCH (n)-[r]-() WHERE r.source = 'plot' WITH DISTINCT r
                      MATCH (t:Title {qid: r.title_qid})
                      RETURN {title_qid: r.title_qid, title: t.title, episode: r.episode, order: t.release_order,
                              subject: coalesce(startNode(r).label, startNode(r).name), relation: type(r),
                              object: coalesce(endNode(r).label, endNode(r).name),
                              evidence: r.evidence, note: r.note} }"""


def facts_text(facts, plots):
    """Fact lines in story order: by title (release order), episode, then where the evidence sentence
    appears in the title's plot. A fact whose evidence isn't found comes last in its episode."""
    texts = {}

    def position(f):
        qid = f["title_qid"]
        if qid not in texts:
            texts[qid] = title_text(plots[qid]) if qid in plots else ""
        found = texts[qid].find(f["evidence"])
        return found if found >= 0 else len(texts[qid]) + 1

    ordered = sorted(facts, key=lambda f: (f["order"], f["episode"] or 0, position(f), f["relation"], f["subject"],
                                           f["object"]))
    return "\n".join(fact_line(f) for f in ordered)


def title_inputs(titles, plots, outputs, max_chars=MAX_INPUT_CHARS):
    """[(kind, id, input or None)]: a digest input per title; a title too long for one input gets
    an input per season, and its digest is written from the season digests once they exist."""
    items = []
    for t in titles:
        plot = plots[t["qid"]]
        header = f"{t['title']} ({t['type']}, {t['year']}; universe {t['universe']}; reality {t['reality']})"
        whole = make_input("title", t["qid"], t["title"], 1, [t["qid"]], f"{header}\n\n{title_text(plot)}")
        if len(whole["text"]) <= max_chars:
            items.append(("title", t["qid"], whole))
            continue
        seasons = sorted({e["season"] for e in plot["episodes"] if e.get("summary_text")})
        for s in seasons:
            season_plot = dict(plot, episodes=[e for e in plot["episodes"] if e["season"] == s])
            sid = f"{t['qid']}-s{s}"
            items.append(("season", sid, make_input("season", sid, f"{t['title']}, season {s}", 1, [t["qid"]],
                                                    f"{header}, season {s}\n\n{title_text(season_plot)}")))
        note = f"{header}. Written from its season digests: its plot is too long for one input."
        items.append(("title", t["qid"], _group("title", t["qid"], t["title"], 1,
                                                [("season", f"{t['qid']}-s{s}") for s in seasons], outputs, note)))
    return items


def character_inputs(session, plots):
    inputs = []
    for r in session.run(f"""MATCH (n:Character)
            WITH n, COUNT {{ (n)-[x]-() WHERE x.source = 'plot' }} AS facts,
                 COUNT {{ (n)-[:APPEARS_IN]->() }} AS titles
            RETURN n.id AS id, n.label AS label, n.profile AS profile, facts, titles, {PLOT_FACTS} AS plot_facts"""):
        if not is_main_character(r["facts"], r["titles"]):
            continue
        if not r["profile"]:
            raise RuntimeError("characters have no profile; run src.graph.profiles first")
        text = r["profile"]
        if r["plot_facts"]:
            text += "\n\nPlot facts (story order):\n" + facts_text(r["plot_facts"], plots)
        inputs.append(make_input("character", r["id"], r["label"], 1,
                                 sorted({f["title_qid"] for f in r["plot_facts"]}), text))
    return inputs


def team_inputs(session, plots):
    inputs = []
    for r in session.run(f"""MATCH (n:Team)
            RETURN n.id AS id, n.name AS name, n.kind AS kind, n.reality AS reality, n.aliases AS aliases,
                   COLLECT {{ MATCH (c:Character)-[m:MEMBER_OF]->(n) WHERE m.source <> 'plot'
                              RETURN {{label: c.label, reality: c.reality, role: m.role, status: m.status}} }}
                     AS members,
                   {PLOT_FACTS} AS plot_facts"""):
        if not r["plot_facts"]:
            continue        # like a character: no plot fact, no written summary (the Defenders)
        members = {}
        for m in r["members"]:
            members.setdefault((m["label"], m["reality"]), []).append(m)
        lines = [f"{r['name']} ({r['kind']}, {r['reality']})."
                 + (f" Also known as: {', '.join(r['aliases'])}." if r["aliases"] else ""),
                 "", "Members (from the wikis):"]
        lines += [f"- {label} ({reality}): {memberships_text(ms)}" for (label, reality), ms in sorted(members.items())]
        if r["plot_facts"]:
            lines += ["", "Plot facts (story order):", facts_text(r["plot_facts"], plots)]
        inputs.append(make_input("team", r["id"], r["name"], 1,
                                 sorted({f["title_qid"] for f in r["plot_facts"]}), "\n".join(lines)))
    return inputs


def series_chains(session):
    """[(first title qid, first title, [qids in release order])] for each FOLLOWS chain."""
    chains = []
    for r in session.run("""MATCH p = (last:Title)-[:FOLLOWS*]->(first:Title)
                            WHERE NOT ()-[:FOLLOWS]->(last) AND NOT (first)-[:FOLLOWS]->()
                            RETURN first.qid AS qid, first.title AS title,
                                   [n IN nodes(p) | [n.release_order, n.qid]] AS members"""):
        chains.append((r["qid"], r["title"], [q for _, q in sorted(r["members"])]))
    return sorted(chains)


def _fits(inp, max_chars):
    return inp is None or len(inp["text"]) <= max_chars


def _universe_from_phases(universe, by_order, phases, outputs):
    """A universe written from the phases its titles are in, plus its titles in no phase."""
    own = [t for t in by_order if t["universe"] == universe]
    used = [p for p in phases if any(p in t["phases"] for t in own)]
    others = [t["title"] for t in by_order if t["universe"] != universe and set(t["phases"]) & set(used)]
    note = (f"Written from the summaries of the phases its titles are in"
            + (f". These phases also cover titles of other universes: {', '.join(others)}." if others else "."))
    members = [("phase", p) for p in used] + [("title", t["qid"]) for t in own if not t["phases"]]
    return _group("universe", universe, universe, 2, members, outputs, note)


def _reality_from_universes(reality, by_order, outputs):
    """A reality written from its universes' summaries, each taken whole."""
    universes = sorted({t["universe"] for t in by_order if t["reality"] == reality})
    others = [f"{t['title']} ({t['reality']})" for t in by_order if t["universe"] in universes and t["reality"] != reality]
    note = (f"Written from the summaries of its universes"
            + (f". Of their titles, these are in other realities: {', '.join(others)}." if others else "."))
    return _group("reality", reality, reality, 3, [("universe", u) for u in universes], outputs, note)


def group_inputs(titles, chains, outputs, max_chars=MAX_INPUT_CHARS):
    """Level 2 and 3 inputs: [(kind, id, the input, or None while a summary below is missing)].
    A universe or reality too big from title digests is built from the level that covers it."""
    by_order = sorted(titles, key=lambda t: t["release_order"])
    items = [("series", qid, group_input("series", qid, f"{name} series", 2, "title", members, outputs))
             for qid, name, members in chains]
    phases = list(dict.fromkeys(p for t in by_order for p in t["phases"]))     # in order of first release
    for phase in phases:
        members = [t["qid"] for t in by_order if phase in t["phases"]]
        items.append(("phase", phase, group_input("phase", phase, phase, 2, "title", members, outputs)))
    for universe in sorted({t["universe"] for t in titles}):
        members = [t["qid"] for t in by_order if t["universe"] == universe]
        inp = group_input("universe", universe, universe, 2, "title", members, outputs)
        if not _fits(inp, max_chars):
            inp = _universe_from_phases(universe, by_order, phases, outputs)
        items.append(("universe", universe, inp))
    for saga in sorted({s for t in titles for s in t["sagas"]}):
        members = [p for p in phases if any(saga in t["sagas"] and p in t["phases"] for t in titles)]
        items.append(("saga", saga, group_input("saga", saga, saga, 3, "phase", members, outputs)))
    title_reality = {t["qid"]: t["reality"] for t in titles}
    title_universe = {t["qid"]: t["universe"] for t in titles}
    for reality in sorted(set(title_reality.values())):
        if len({title_universe[q] for q, r in title_reality.items() if r == reality}) > 1:
            sources = reality_sources(reality, title_reality, title_universe)
            inp = _group("reality", reality, reality, 3, sources, outputs)
            if not _fits(inp, max_chars):
                inp = _reality_from_universes(reality, by_order, outputs)
            items.append(("reality", reality, inp))
    return items


def read_outputs(outputs_dir=OUTPUTS_DIR):
    outputs = {}
    for path in outputs_dir.glob("*/*.json"):
        output = read_json(path)
        outputs[(path.parent.name, output["id"])] = output
    return outputs


def build(session, plots, outputs):
    """(the inputs that can be built now, {kind: how many wait for the summaries below them})."""
    titles = [r.data() for r in session.run(
        "MATCH (t:Title) RETURN t.qid AS qid, t.title AS title, t.type AS type, t.year AS year, "
        "t.universe AS universe, t.reality AS reality, t.phases AS phases, t.sagas AS sagas, "
        "t.release_order AS release_order ORDER BY t.release_order")]
    built = character_inputs(session, plots) + team_inputs(session, plots)
    waiting = {}
    for kind, _, inp in title_inputs(titles, plots, outputs) + group_inputs(titles, series_chains(session), outputs):
        if inp:
            built.append(inp)
        else:
            waiting[kind] = waiting.get(kind, 0) + 1
    return built, waiting


def read_plots():
    plots = {}
    for path in sorted(PLOTS_DIR.glob("*.json")):
        plot = read_json(path)
        plots[plot["title_qid"]] = plot
    return plots


def input_path(inp):
    return INPUTS_DIR / inp["kind"] / file_name(inp["id"])


def main():
    # Upper levels are built only from kept summaries (two passing checks in a row). The import is
    # here because summary_status itself builds on this module.
    from src.graph.summary_status import kept_outputs
    outputs = read_outputs()
    with connect() as driver, driver.session() as session:
        built, waiting = build(session, read_plots(), kept_outputs())
    for inp in built:
        write_if_changed(input_path(inp), inp)
    current = {input_path(i) for i in built}
    for stale in sorted(p for p in INPUTS_DIR.glob("*/*.json") if p not in current):
        stale.unlink()      # an input no longer built, such as a title now split by season
        print(f"removed stale input {stale.relative_to(PROJECT_ROOT)}")
    pending = [i for i in built if is_pending(i, outputs.get((i["kind"], i["id"])))]
    for kind in dict.fromkeys(i["kind"] for i in built):
        of_kind = [i for i in built if i["kind"] == kind]
        print(f"{kind:10} {len(of_kind):4} inputs, {sum(i in pending for i in of_kind):4} to write")
    for kind, n in waiting.items():
        print(f"{kind:10} {n:4} waiting for the summaries below them to be kept")
    for i in sorted((i for i in built if len(i["text"]) > MAX_INPUT_CHARS), key=lambda i: -len(i["text"])):
        print(f"over {MAX_INPUT_CHARS:,} characters: {i['kind']} {i['name']} ({len(i['text']):,})")
    print("Next actions and their batches: src.graph.summary_status")


if __name__ == "__main__":
    main()
