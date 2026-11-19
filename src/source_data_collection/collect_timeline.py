"""Collect the MCU's in-universe timeline from two sources (the expert's order of trust is the
Disney+ timeline, then the MCU wiki; Disney+ publishes its current order only as an image):

- MCU wiki "Chronological Order/Viewing Timeline": every film and episode in chronological
  viewing order, with in-universe dates and release dates.
- Wikipedia "Marvel Cinematic Universe timeline": each title placed in an in-universe year,
  using the official timeline book and then the Disney+ timeline.

Needs:  build_title_registry
Output: source_data/fandom/mcu_wiki_viewing_timeline.json  (raw page, as collected)
        source_data/fandom/viewing_timeline.csv            (one row per film or episode, in order)
        source_data/wikipedia/timeline.json                (raw section, as collected)
        source_data/wikipedia/timeline_years.csv           (one row per title placement, in order)
Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.collect_timeline
"""

import re

import mwparserfromhell
from mwparserfromhell.nodes import Wikilink

from src.source_data_collection.build_title_registry import (
    P_PART_OF_THE_SERIES,
    P_SERIES_ORDINAL,
    REGISTRY_PATH,
)
from src.source_data_collection.cast_matching import normalize_name
from src.source_data_collection.collect_characters import FANDOM_DIR, FANDOM_LICENSE, MCU_WIKI
from src.source_data_collection.collect_phases import WIKIPEDIA_DIR, title_scope
from src.source_data_collection.storage import read_csv, utc_now, write_csv, write_json
from src.source_data_collection.wikipedia_cast import WIKIPEDIA_LICENSE
from src.source_data_collection.wikitext import member_links, plain_text
from src.title_types import is_movie
from src.utils import FandomClient, WikimediaClient, enwiki_url, qualifier_value

TIMELINE_ARTICLE = "Marvel Cinematic Universe timeline"
TIMELINE_ROW_TEMPLATE = "marvel cinematic universe timeline/row"
VIEWING_TIMELINE_PAGE = "Chronological Order/Viewing Timeline"

VIEWING_RAW_PATH = FANDOM_DIR / "mcu_wiki_viewing_timeline.json"
VIEWING_TIMELINE_PATH = FANDOM_DIR / "viewing_timeline.csv"
WIKIPEDIA_TIMELINE_RAW_PATH = WIKIPEDIA_DIR / "timeline.json"
WIKIPEDIA_TIMELINE_PATH = WIKIPEDIA_DIR / "timeline_years.csv"

_ERA_YEAR = re.compile(r"(\d{1,4})\s*(B\.?\s?C\.?|A\.?\s?D\.?)", re.IGNORECASE)
_YEAR = re.compile(r"\b(\d{4})\b")
_EPISODE = re.compile(r"^(.*?): (\d+)\.(\d+)")


def years_of(text):
    """(first, last) year mentioned in a date text; years B.C. are negative."""
    era = [(-int(n) if e.upper().startswith("B") else int(n)) for n, e in _ERA_YEAR.findall(text)]
    years = era or [int(y) for y in _YEAR.findall(text)]
    return (min(years), max(years)) if years else (None, None)


def wikipedia_year_rows(wikitext):
    """Each linked title in the timeline diagram, in order, with its in-universe years."""
    rows = []
    for template in mwparserfromhell.parse(wikitext).filter_templates():
        if str(template.name).strip().lower() != TIMELINE_ROW_TEMPLATE:
            continue
        year = str(template.get("year").value).strip() if template.has("year") else ""
        first, last = years_of(year)
        for param in template.params:
            if param.showkey:
                continue
            for link in member_links(str(param.value)):
                rows.append({"position": len(rows) + 1, "page": link["page"], "year_text": year,
                             "start_year": first, "end_year": last})
    return rows


def _cell_text(cell):
    return plain_text(re.sub(r'^\s*data-row-id="[^"]*"\s*\|', "", cell))


def mcu_wiki_rows(wikitext):
    """One row per film or episode of the viewing table, in order: display title, dates,
    release date and media type (the cells after the title cell)."""
    rows = []
    for chunk in re.split(r"\n\|-", wikitext):
        cells = [line[1:] for line in chunk.split("\n") if line.startswith("|") and not line.startswith(("|-", "|}"))]
        title_at = next((i for i, c in enumerate(cells) if "''[[" in c and "[[File:" not in c), None)
        if title_at is None or len(cells) < title_at + 4:
            continue
        link = next(iter(mwparserfromhell.parse(cells[title_at]).filter_wikilinks()))
        display = plain_text(str(link.text)) if link.text else str(link.title).strip()
        rows.append({"position": len(rows) + 1, "page": str(link.title).strip(), "display": display,
                     "dates": _cell_text(cells[title_at + 1]),
                     "release_date": _cell_text(cells[title_at + 2]),
                     "media_type": _cell_text(cells[title_at + 3])})
    return rows


def match_viewing_row(row, titles):
    """QID of the title in scope that a viewing-table row (a film, or 'Show: S.EE: ...') is part of."""
    episode = _EPISODE.match(row["display"])
    name = normalize_name(episode.group(1) if episode else row["display"])
    season = int(episode.group(2)) if episode else None
    for t in titles:
        t_name, t_seasons = title_scope(t)
        if t_name != name or (episode and is_movie(t)):
            continue
        if season is None or t_seasons is None or season in t_seasons:
            return t["wikidata_qid"]
    return ""


def placement_qid(page_qid, entities, titles):
    """QID of the title in scope a Wikipedia placement is about: the page's own item, or the
    series in scope when the page is one of its seasons ('Daredevil season 1')."""
    in_scope = {t["wikidata_qid"]: t for t in titles}
    if page_qid in in_scope:
        return page_qid
    series_qid, number = qualifier_value(entities.get(page_qid) or {}, P_PART_OF_THE_SERIES, P_SERIES_ORDINAL)
    series = in_scope.get(series_qid)
    if not series or not number or not number.isdigit():
        return ""
    _, seasons = title_scope(series)
    return series_qid if seasons is None or int(number) in seasons else ""


def main():
    retrieved_at = utc_now()
    titles = read_csv(REGISTRY_PATH)
    wikimedia, fandom = WikimediaClient(), FandomClient()

    viewing = fandom.page(MCU_WIKI, VIEWING_TIMELINE_PAGE)
    write_json(VIEWING_RAW_PATH, {**viewing, "source": "mcu_wiki", "retrieved_at": retrieved_at,
                                  "license": FANDOM_LICENSE})
    viewing_rows = [{**r, "title_qid": match_viewing_row(r, titles), "source": "mcu_wiki",
                     "source_url": viewing["url"], "revid": viewing["revid"],
                     "retrieved_at": retrieved_at, "license": FANDOM_LICENSE}
                    for r in mcu_wiki_rows(viewing["wikitext"])]
    write_csv(VIEWING_TIMELINE_PATH, viewing_rows)

    section = wikimedia.top_level_section(TIMELINE_ARTICLE, prefix="Timeline")
    url = enwiki_url(section["page"])
    write_json(WIKIPEDIA_TIMELINE_RAW_PATH, {**section, "source": "wikipedia", "source_url": url,
                                             "retrieved_at": retrieved_at, "license": WIKIPEDIA_LICENSE})
    year_rows = wikipedia_year_rows(section["wikitext"])
    pages = wikimedia.resolve_enwiki_titles(list(dict.fromkeys(r["page"] for r in year_rows)))
    in_scope = {t["wikidata_qid"] for t in titles}
    other_qids = sorted({p["qid"] for p in pages.values() if p["qid"] and p["qid"] not in in_scope})
    entities = wikimedia.get_entities(other_qids, props="claims")
    write_csv(WIKIPEDIA_TIMELINE_PATH, [
        {**r, "title_qid": placement_qid(pages[r["page"]]["qid"], entities, titles),
         "source": "wikipedia", "source_url": url, "revid": section["revid"],
         "retrieved_at": retrieved_at, "license": WIKIPEDIA_LICENSE} for r in year_rows])
    print(f"MCU wiki: {len(viewing_rows)} rows, {sum(bool(r['title_qid']) for r in viewing_rows)} in scope; "
          f"Wikipedia: {len(year_rows)} placements")


if __name__ == "__main__":
    main()
