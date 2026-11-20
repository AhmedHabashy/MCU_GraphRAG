"""Collect Tier 1 plot summaries (films) and episode summaries (series, seasons) from Wikipedia.

Films use the "Plot" section, or "Premise" while unreleased. Series and seasons use the
"Episodes" section, following season pages pulled in with {{:Page}}. For cross-checking,
the matching Wikidata episode items are saved as well.

Needs:  source_data/wikidata/titles.csv and entities.json (build_title_registry)
Output: source_data/wikipedia/plots/<title QID>.json      (section wikitext, plain text, episodes)
        source_data/wikidata/episode_entities.json   (raw Wikidata episode items per title)
Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.collect_plots
"""

import re

from src.source_data_collection.build_title_registry import (
    ENTITIES_PATH, P_HAS_PARTS, P_INSTANCE_OF, P_PART_OF_THE_SERIES, P_SERIES_ORDINAL, REGISTRY_PATH,
    SEASON, WIKIDATA_LICENSE,
)
from src.source_data_collection.incremental import TitleScopes
from src.source_data_collection.storage import read_csv, read_json, utc_now, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.source_data_collection.wikipedia_cast import WIKIPEDIA_LICENSE
from src.source_data_collection.wikitext import episode_entries, plain_text, transcluded_pages
from src.title_types import is_movie
from src.utils import WikimediaClient, claim_values, enwiki_url, qualifier_value

PLOTS_DIR = PROJECT_ROOT / "source_data" / "wikipedia" / "plots"
EPISODE_ENTITIES_PATH = PROJECT_ROOT / "source_data" / "wikidata" / "episode_entities.json"

FILM_HEADINGS = ("Plot", "Premise")  # "Premise" only for unreleased films
EPISODES_HEADING = "Episodes"
Q_TV_EPISODE = "Q21191270"


def plot_path(title_qid):
    return PLOTS_DIR / f"{title_qid}.json"


def _section_meta(section):
    return {"page": section["page"], "revid": section["revid"], "heading": section["heading"],
            "url": enwiki_url(section["page"]), "wikitext": section["wikitext"]}


_SUBHEADING = re.compile(r"^===\s*(.*?)\s*===\s*$", re.MULTILINE)
_SEASON_HEADING = re.compile(r"^Season (\d+)", re.IGNORECASE)


def _episodes(section, season, retrieved_at, wanted=frozenset()):
    """Episodes of a section; a 'Season N' subheading inside it sets the season of the episodes
    below it (I Am Groot lists both seasons in one section). An episode has aired when it has
    a full air date on or before the collection day; announced episodes are kept but marked."""
    today = retrieved_at[:10]
    parts = _SUBHEADING.split(section["wikitext"])   # [text, heading, text, heading, text, ...]
    episodes = []
    for i in range(0, len(parts), 2):
        if i:
            match = _SEASON_HEADING.match(plain_text(parts[i - 1]))
            season = int(match.group(1)) if match else season
        if wanted and season not in wanted:
            continue
        episodes += [{**e, "season": season, "source_page": section["page"],
                      "aired": bool(e["air_date"]) and e["air_date"] <= today}
                     for e in episode_entries(parts[i])]
    return episodes


def _season_from_page(page):
    match = re.search(r"season (\d+)", page)
    return int(match.group(1)) if match else None


def _season_pages(section, client, sections):
    """Season pages an Episodes section transcludes. A transcluded page with no season number
    is an episode list ('List of Agents of S.H.I.E.L.D. episodes'): its own season pages are
    used, and its section is appended to `sections` for provenance."""
    pages = []
    for page in transcluded_pages(section["wikitext"]):
        if _season_from_page(page) is not None:
            pages.append(page)
            continue
        listing = client.top_level_section(page, prefix=EPISODES_HEADING)
        if listing:
            sections.append(listing)
            pages += [p for p in transcluded_pages(listing["wikitext"]) if _season_from_page(p) is not None]
    return pages


def plot_record(title, client, retrieved_at):
    """Plot text (films) or episode summaries (series and seasons) for one title."""
    sections, text, episodes, kind = [], "", [], ""
    if is_movie(title):
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
            wanted = selected_seasons(title)
            sections, episodes = [section], _episodes(section, season, retrieved_at, wanted)
            for page in _season_pages(section, client, sections):
                if wanted and _season_from_page(page) not in wanted:
                    continue
                season_section = client.top_level_section(page, prefix=EPISODES_HEADING)
                if season_section:
                    sections.append(season_section)
                    episodes += _episodes(season_section, _season_from_page(page), retrieved_at)
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

    # Only new or changed titles are collected; the others keep their stored records.
    scopes = TitleScopes("plots")
    stored = read_json(EPISODE_ENTITIES_PATH) if EPISODE_ENTITIES_PATH.exists() else {"by_title": {}}
    stored_at = stored.get("retrieved_at_by_title") or dict.fromkeys(stored["by_title"], stored.get("retrieved_at"))
    in_scope = {t["wikidata_qid"] for t in titles}
    episode_entities = {q: e for q, e in stored["by_title"].items() if q in in_scope}
    episodes_at = {q: stored_at[q] for q in episode_entities}
    todo = scopes.to_collect(titles)
    for title in todo:
        record = plot_record(title, client, retrieved_at)
        write_json(plot_path(title["wikidata_qid"]), record)
        if not is_movie(title):
            episode_entities[title["wikidata_qid"]] = wikidata_episodes(
                title_entities[title["wikidata_qid"]], client, selected_seasons(title))
            episodes_at[title["wikidata_qid"]] = retrieved_at
        print(f"{title['title']}: {record['kind'] or 'MISSING'} "
              f"({len(record['episodes'])} episodes)", flush=True)

    write_json(EPISODE_ENTITIES_PATH, {"retrieved_at": retrieved_at, "retrieved_at_by_title": episodes_at,
                                       "source": "wikidata", "license": WIKIDATA_LICENSE,
                                       "by_title": episode_entities})
    scopes.save(titles)
    print(f"Plots collected for {len(todo)}/{len(titles)} titles")


if __name__ == "__main__":
    main()
