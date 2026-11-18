"""Collect Tier 1 plot summaries (films) and episode summaries (series, seasons) from Wikipedia.

Films use the "Plot" section, or "Premise" while unreleased. Series and seasons use the
"Episodes" section, following season pages pulled in with {{:Page}}. For cross-checking,
the matching Wikidata episode items are saved as well.

Needs:  source_data/wikidata/tier1_titles.csv and tier1_entities.json (build_title_registry)
Output: source_data/wikipedia/plots/<title QID>.json      (section wikitext, plain text, episodes)
        source_data/wikidata/tier1_episode_entities.json   (raw Wikidata episode items per title)
Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.collect_plots
"""

import re

from src.source_data_collection.build_title_registry import (
    ENTITIES_PATH, P_HAS_PARTS, P_INSTANCE_OF, P_PART_OF_THE_SERIES, P_SERIES_ORDINAL, REGISTRY_PATH,
    SEASON, WIKIDATA_LICENSE,
)
from src.source_data_collection.storage import read_csv, read_json, utc_now, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.source_data_collection.wikipedia_cast import WIKIPEDIA_LICENSE
from src.source_data_collection.wikitext import episode_entries, plain_text, transcluded_pages
from src.utils import WikimediaClient, claim_values, enwiki_url, qualifier_value

PLOTS_DIR = PROJECT_ROOT / "source_data" / "wikipedia" / "plots"
EPISODE_ENTITIES_PATH = PROJECT_ROOT / "source_data" / "wikidata" / "tier1_episode_entities.json"

FILM_HEADINGS = ("Plot", "Premise")  # "Premise" only for unreleased films
EPISODES_HEADING = "Episodes"
Q_TV_EPISODE = "Q21191270"


def plot_path(title_qid):
    return PLOTS_DIR / f"{title_qid}.json"


def _section_meta(section):
    return {"page": section["page"], "revid": section["revid"], "heading": section["heading"],
            "url": enwiki_url(section["page"]), "wikitext": section["wikitext"]}


def _episodes(section, season):
    return [{**e, "season": season, "source_page": section["page"]}
            for e in episode_entries(section["wikitext"])]


def _season_from_page(page):
    match = re.search(r"season (\d+)", page)
    return int(match.group(1)) if match else None


def plot_record(title, client, retrieved_at):
    """Plot text (films) or episode summaries (series and seasons) for one title."""
    sections, text, episodes, kind = [], "", [], ""
    if title["type"] == "Film":
        section = client.top_level_section(title["enwiki_title"], prefix=FILM_HEADINGS)
        if section:
            sections = [section]
            kind = "plot" if section["heading"].startswith("Plot") else "premise"
            text = plain_text(section["wikitext"])
    else:
        section = client.top_level_section(title["enwiki_title"], prefix=EPISODES_HEADING)
        if section:
            kind = "episodes"
            season = int(title["season_number"]) if title["type"] == SEASON else 1
            sections, episodes = [section], _episodes(section, season)
            wanted = selected_seasons(title)
            for page in transcluded_pages(section["wikitext"]):
                if wanted and _season_from_page(page) not in wanted:
                    continue
                season_section = client.top_level_section(page, prefix=EPISODES_HEADING)
                if season_section:
                    sections.append(season_section)
                    episodes += _episodes(season_section, _season_from_page(page))
    return {"title": title["title"], "title_qid": title["wikidata_qid"], "type": title["type"],
            "kind": kind, "text": text, "episodes": episodes,
            "sections": [_section_meta(s) for s in sections],
            "source": "wikipedia", "retrieved_at": retrieved_at, "license": WIKIPEDIA_LICENSE}


def selected_seasons(title):
    """Season numbers a series is limited to in the tier list, or an empty set for all."""
    return {int(s) for s in title.get("seasons", "").split("|") if s}


def wikidata_episodes(entity, client, seasons=frozenset()):
    """Episode items under a season, or under each season of a series (via P527); for a
    series limited to some seasons, only seasons whose series ordinal is selected."""
    parts = claim_values(entity, P_HAS_PARTS)
    fetched = client.get_entities(parts, props="labels|claims")
    episodes, nested = [], []
    for qid in parts:
        part = fetched.get(qid)
        if not part:
            continue
        if Q_TV_EPISODE in claim_values(part, P_INSTANCE_OF):
            episodes.append(part)
            continue
        _, ordinal = qualifier_value(part, P_PART_OF_THE_SERIES, P_SERIES_ORDINAL)
        if not seasons or (ordinal or "").isdigit() and int(ordinal) in seasons:
            nested += claim_values(part, P_HAS_PARTS)
    if nested:
        deeper = client.get_entities(nested, props="labels|claims")
        episodes += [deeper[q] for q in nested if q in deeper]
    return episodes


def main():
    titles = read_csv(REGISTRY_PATH)
    title_entities = read_json(ENTITIES_PATH)["entities"]
    retrieved_at = utc_now()
    client = WikimediaClient()

    episode_entities = {}
    for title in titles:
        record = plot_record(title, client, retrieved_at)
        write_json(plot_path(title["wikidata_qid"]), record)
        if title["type"] != "Film":
            episode_entities[title["wikidata_qid"]] = wikidata_episodes(
                title_entities[title["wikidata_qid"]], client, selected_seasons(title))
        print(f"{title['title']}: {record['kind'] or 'MISSING'} "
              f"({len(record['episodes'])} episodes)", flush=True)

    write_json(EPISODE_ENTITIES_PATH, {"retrieved_at": retrieved_at, "source": "wikidata",
                                       "license": WIKIDATA_LICENSE, "by_title": episode_entities})


if __name__ == "__main__":
    main()
