"""Character profiles: a short text per character, built from the graph without an LLM.

A profile says who a character is: names, reality, species, actors, appearances in release order,
wiki team memberships and variants (from the data, not the plot facts). Retrieval returns it as
context, so a character always comes with its reality, actor and titles. Plot facts are left
to the written summaries (docs/rag_design.md, "Summaries").

Stored as Character.profile. Run after src.graph.load_neo4j, which rebuilds the graph.
Run:  .venv\\Scripts\\python.exe -m src.graph.profiles
"""

from src.graph.load_neo4j import run_batches
from src.graph.neo4j_db import connect

MAX_VARIANT_TITLES = 3

PROFILE_FACTS = """
MATCH (c:Character)
RETURN c.id AS id, c.label AS label, c.reality AS reality, c.aliases AS aliases, c.species AS species,
  COLLECT { MATCH (p:Person)-[r:PLAYS]->(c)
            WITH p, count(DISTINCT r.title_qid) AS n, collect(r.credited_as) AS credit_lists
            RETURN {name: p.name, titles: n,
                    credits: reduce(all = [], l IN credit_lists | all + [x IN l WHERE NOT x IN all])} } AS actors,
  COLLECT { MATCH (c)-[:APPEARS_IN]->(t:Title)
            RETURN {title: t.title, year: t.year, order: t.release_order} } AS titles,
  COLLECT { MATCH (c)-[m:MEMBER_OF]->(t:Team) WHERE m.source <> 'plot'
            RETURN {team: t.name, role: m.role, status: m.status} } AS teams,
  COLLECT { MATCH (c)-[v:VARIANT_OF]-(o:Character) WHERE v.source IS NULL
            WITH DISTINCT o
            RETURN {label: o.label, reality: o.reality,
                    titles: COLLECT { MATCH (o)-[:APPEARS_IN]->(t:Title) RETURN t.title ORDER BY t.release_order }} }
    AS variants
"""


def _count(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _credits_matter(actors):
    """Credits tell actors apart (a young version, a voice) only when several actors play the
    character or one of them is a voice; otherwise they would only repeat the name."""
    return len(actors) > 1 or any("voice" in credit.casefold() for a in actors for credit in a.get("credits", []))


def _actor_text(actor, with_credits):
    text = f"{actor['name']} ({_count(actor['titles'], 'title')}"
    credits = [c for c in actor.get("credits", []) if c]
    if with_credits and credits:
        text += ", as " + ", ".join(f'"{c}"' for c in credits)
    return text + ")"


def memberships_text(memberships):
    """One team's memberships, each role with its own status: "founder (current), leader (former)"."""
    pairs = sorted({(m["role"], m["status"]) for m in memberships})
    return ", ".join(f"{role} ({status})" for role, status in pairs)


def profile_text(c):
    """The profile of one character (a row of PROFILE_FACTS); fields without data are left out."""
    seen = {c["label"].casefold()}
    aliases = []
    for alias in c["aliases"]:
        if alias.casefold() not in seen:
            seen.add(alias.casefold())
            aliases.append(alias)
    lines = [f"{c['label']} ({c['reality']})." + (f" Also known as: {', '.join(aliases)}." if aliases else "")]
    if c["species"]:
        lines.append(f"Species: {', '.join(c['species'])}.")
    if c["actors"]:
        actors = sorted(c["actors"], key=lambda a: (-a["titles"], a["name"]))
        lines.append("Played by: " + ", ".join(_actor_text(a, _credits_matter(actors)) for a in actors) + ".")
    if c["titles"]:
        titles = sorted(c["titles"], key=lambda t: t["order"])
        lines.append("Appears in (release order): " + ", ".join(f"{t['title']} ({t['year']})" for t in titles) + ".")
    if c["teams"]:
        teams = {}
        for m in c["teams"]:
            teams.setdefault(m["team"], []).append(m)
        lines.append("Teams: " + "; ".join(f"{team}: {memberships_text(ms)}" for team, ms in sorted(teams.items())) + ".")
    if c["variants"]:
        variants = sorted(c["variants"], key=lambda v: (v["reality"], v["label"]))
        lines.append("Variants: " + ", ".join(
            f"{v['label']} ({v['reality']}: {', '.join(v['titles'][:MAX_VARIANT_TITLES])}"
            f"{', ...' if len(v['titles']) > MAX_VARIANT_TITLES else ''})" for v in variants) + ".")
    return "\n".join(lines)


def write_profiles(session):
    rows = [{"id": r["id"], "profile": profile_text(r)} for r in session.run(PROFILE_FACTS)]
    run_batches(session, "UNWIND $rows AS r MATCH (c:Character {id: r.id}) SET c.profile = r.profile", rows)
    return len(rows)


def main():
    with connect() as driver, driver.session() as session:
        print(f"Wrote {write_profiles(session)} character profiles")


if __name__ == "__main__":
    main()
