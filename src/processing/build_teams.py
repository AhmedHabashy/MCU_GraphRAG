"""Build teams and team memberships: each wiki member row linked to a character.

A member is linked by its exact wiki page (Marvel Database or MCU wiki page of a character),
which also links members from other realities (e.g. Bishop in the X-Men '97 team); otherwise
by name, but only to a character in the team's reality that is the single match.

Needs:  collect_teams, build_characters
Output: processed_data/teams/teams.csv        (team_id, name, reality, kind, aliases)
        processed_data/teams/memberships.csv  (team, character, role, current/former, source)
Run:    .venv\\Scripts\\python.exe -m src.processing.build_teams
"""

import re

from src.processing.build_characters import ALIASES_PATH, CHARACTERS_PATH
from src.source_data_collection.cast_matching import normalize_name
from src.source_data_collection.collect_characters import MARVEL_DB_WIKI
from src.source_data_collection.collect_teams import TEAM_ALIASES_PATH, TEAM_MEMBERS_PATH, load_teams
from src.source_data_collection.storage import read_csv, write_csv
from src.source_data_collection.tier_titles import PROJECT_ROOT

TEAMS_DIR = PROJECT_ROOT / "processed_data" / "teams"
TEAMS_PATH = TEAMS_DIR / "teams.csv"
MEMBERSHIPS_PATH = TEAMS_DIR / "memberships.csv"

_EARTH_SUFFIX = re.compile(r"\s*\((Earth-[^)]+)\)$")


def team_id(name, reality):
    return f"{name}@{reality}"


def _same_page(a, b):
    return bool(a) and a.replace("_", " ") == b.replace("_", " ")


def resolve_member(member, reality, characters, aliases):
    """(character_id, how) for a wiki member row; ('', '') when nothing fits."""
    page_field = "marvel_db_page" if member["source"] == MARVEL_DB_WIKI else "mcu_wiki_page"
    by_page = [c["character_id"] for c in characters if _same_page(c[page_field], member["page"])]
    if by_page:
        in_reality = [c for c in by_page if c.endswith(f"@{reality}")]
        return (in_reality or by_page)[0], page_field
    # The page name (often a real name) before the display name (often a shared codename, e.g.
    # 'Iron Fist' is also Davos); among several characters with a name, the one it labels.
    in_reality = [c for c in characters if c["reality"] == reality]
    for name in dict.fromkeys(normalize_name(n) for n in (_EARTH_SUFFIX.sub("", member["page"]), member["name"])):
        by_name = [c for c in in_reality if name in aliases.get(c["character_id"], set())]
        labelled = [c for c in by_name if normalize_name(c["label"]) == name]
        for found in (by_name, labelled):
            if len(found) == 1:
                return found[0]["character_id"], "name"
    return "", ""


def team_rows(teams, wiki_aliases):
    rows = []
    for t in teams:
        names = [t["also called"]] + [a["alias"] for a in wiki_aliases
                                      if a["team"] == t["team"] and a["reality"] == t["reality"]]
        rows.append({"team_id": team_id(t["team"], t["reality"]), "name": t["team"],
                     "reality": t["reality"], "kind": t["kind"], "aliases": "|".join(dict.fromkeys(n for n in names if n)),
                     "source": "curated"})
    return rows


def membership_rows(members, characters, aliases):
    rows = []
    for m in members:
        cid, how = resolve_member(m, m["reality"], characters, aliases)
        rows.append({"team_id": team_id(m["team"], m["reality"]), "character_id": cid,
                     "member_page": m["page"], "member_name": m["name"], "role": m["role"],
                     "status": "former" if m["former"] == "True" else "current",
                     "resolved_by": how, "source": m["source"],
                     "source_url": m.get("source_url", ""), "revid": m.get("revid", "")})
    return rows


def main():
    characters = read_csv(CHARACTERS_PATH)
    aliases = {}
    for a in read_csv(ALIASES_PATH):
        aliases.setdefault(a["character_id"], set()).add(a["normalized"])
    teams = team_rows(load_teams(), read_csv(TEAM_ALIASES_PATH))
    memberships = membership_rows(read_csv(TEAM_MEMBERS_PATH), characters, aliases)
    write_csv(TEAMS_PATH, teams)
    write_csv(MEMBERSHIPS_PATH, memberships)
    print(f"{len(teams)} teams, {len(memberships)} memberships, "
          f"{sum(bool(m['character_id']) for m in memberships)} linked to a character")


if __name__ == "__main__":
    main()
