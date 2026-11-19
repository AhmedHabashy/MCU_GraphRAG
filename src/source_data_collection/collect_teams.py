"""Collect team members, leaders and founders for the curated teams (docs, "Teams") from the
MCU wiki and the Marvel Database, two independent sources.

The wikis give membership as of today (current or former), not per film.

Needs:  docs/data_sources_and_tiers.md ("Teams")
Output: source_data/fandom/teams/<wiki>/<page>.json  (raw infobox section, as collected)
        source_data/wikipedia/teams/<page>.json      (whole Wikipedia team article, wikitext and text)
        source_data/fandom/team_members.csv    (one row per team, source, role and member)
        source_data/fandom/team_aliases.csv    (team names from the Marvel Database)
Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.collect_teams
"""

import re

import mwparserfromhell

from src.source_data_collection.collect_characters import (
    FANDOM_DIR, FANDOM_LICENSE, MARVEL_DB_WIKI, MCU_WIKI,
)
from src.source_data_collection.storage import utc_now, write_csv, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT, TIERS_DOC_PATH, read_table
from src.source_data_collection.wikipedia_cast import WIKIPEDIA_LICENSE
from src.source_data_collection.wikitext import infobox_params, member_links, name_list, plain_text
from src.utils import FandomClient, WikimediaClient

TEAMS_HEADING = "### Teams"
TEAMS_RAW_DIR = FANDOM_DIR / "teams"
TEAM_MEMBERS_PATH = FANDOM_DIR / "team_members.csv"
TEAM_ALIASES_PATH = FANDOM_DIR / "team_aliases.csv"
WIKIPEDIA_TEAMS_DIR = PROJECT_ROOT / "source_data" / "wikipedia" / "teams"

# Infobox templates and their member fields: field -> (role, former)
TEAM_TEMPLATES = ("Marvel Database:Team Template", "Marvel Database:Organization Template", "Organization")
# (Marvel Database fields first, then the MCU wiki's, as each wiki writes them)
MEMBER_FIELDS = {
    "Founders": ("founder", False), "founder": ("founder", False),
    "Leaders": ("leader", False), "leader": ("leader", False), "formerleaders": ("leader", True),
    "CurrentMembers": ("member", False), "members": ("member", False),
    "FormerMembers": ("member", True), "formermembers": ("member", True),
}


def load_teams(path=TIERS_DOC_PATH):
    return read_table(path, TEAMS_HEADING)


def _team_params(wikitext):
    for template in TEAM_TEMPLATES:
        params = infobox_params(wikitext, template)
        if params:
            return params
    return {}


def team_members(wikitext):
    """[{role, page, name, former}] from a team infobox, in field order."""
    params = _team_params(wikitext)
    members = []
    for field, (role, field_former) in MEMBER_FIELDS.items():
        for m in member_links(params.get(field, "")):
            members.append({"role": role, "page": m["page"], "name": m["name"],
                            "former": field_former or m["former"]})
    return members


def team_aliases(wikitext):
    return name_list(_team_params(wikitext).get("Aliases", ""))


def _file_name(page):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", page) + ".json"


def main():
    retrieved_at = utc_now()
    client = FandomClient()
    member_rows, alias_rows = [], []
    for team in load_teams():
        for wiki, page in ((MCU_WIKI, team["mcu wiki page"]), (MARVEL_DB_WIKI, team["marvel database page"])):
            if not page:
                continue
            lead = client.lead(wiki, page)
            if lead is None:
                print(f"WARNING: {wiki}:{page} not found")
                continue
            write_json(TEAMS_RAW_DIR / wiki / _file_name(lead["page"]),
                       {**lead, "team": team["team"], "reality": team["reality"], "source": wiki,
                        "retrieved_at": retrieved_at, "license": FANDOM_LICENSE})
            provenance = {"source": wiki, "source_url": lead["url"], "revid": lead["revid"],
                          "retrieved_at": retrieved_at, "license": FANDOM_LICENSE}
            member_rows += [{"team": team["team"], "reality": team["reality"], **m, **provenance}
                            for m in team_members(lead["wikitext"])]
            alias_rows += [{"team": team["team"], "reality": team["reality"], "alias": a, **provenance}
                           for a in team_aliases(lead["wikitext"])]
    write_csv(TEAM_MEMBERS_PATH, member_rows)
    write_csv(TEAM_ALIASES_PATH, alias_rows)

    wikimedia = WikimediaClient()
    pages = {}
    for team in load_teams():
        if team["wikipedia page"]:
            pages.setdefault(team["wikipedia page"], []).append(team_label(team))
    for page, teams in pages.items():
        article = wikimedia.article(page)
        write_json(WIKIPEDIA_TEAMS_DIR / _file_name(article["page"]),
                   {**article, "text": plain_text(article["wikitext"]), "teams": teams,
                    "source": "wikipedia", "retrieved_at": retrieved_at, "license": WIKIPEDIA_LICENSE})
    print(f"{len(member_rows)} team member rows, {len(alias_rows)} team aliases, "
          f"{len(pages)} Wikipedia team articles")


def team_label(team):
    return f"{team['team']}@{team['reality']}"


if __name__ == "__main__":
    main()
