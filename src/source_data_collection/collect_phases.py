"""Collect which MCU phase each Tier 1 title belongs to, from two independent sources:

- Wikipedia: each "Marvel Cinematic Universe: Phase N" article has one subsection per film or
  series (season) under its Films / Television sections.
- Wikidata: titles are "part of the series" (P179) of their phase and saga items.

The official phase -> saga structure is curated in docs/data_sources_and_tiers.md.

Needs:  build_title_registry
Output: source_data/wikipedia/phases/<Phase N>.json   (raw section headings, as collected)
        source_data/wikipedia/phases.csv        (title -> phase, per heading)
        source_data/wikidata/phases.csv         (title -> phases and sagas)
Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.collect_phases
"""

import html
import re

from src.source_data_collection.build_title_registry import (
    ENTITIES_PATH, P_PART_OF_THE_SERIES, REGISTRY_PATH, SEASON, WIKIDATA_LICENSE,
)
from src.source_data_collection.cast_matching import normalize_name
from src.source_data_collection.storage import read_csv, read_json, utc_now, write_csv, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.source_data_collection.wikipedia_cast import WIKIPEDIA_LICENSE
from src.utils import WikimediaClient, claim_values, enwiki_url, label

PHASES = ["Phase One", "Phase Two", "Phase Three", "Phase Four", "Phase Five", "Phase Six"]
PHASE_ARTICLE = "Marvel Cinematic Universe: {phase}"
PHASE_SECTIONS = ("Film", "Television", "Short")

WIKIPEDIA_DIR = PROJECT_ROOT / "source_data" / "wikipedia"
PHASE_PAGES_DIR = WIKIPEDIA_DIR / "phases"
WIKIPEDIA_PHASES_PATH = WIKIPEDIA_DIR / "phases.csv"
WIKIDATA_PHASES_PATH = PROJECT_ROOT / "source_data" / "wikidata" / "phases.csv"

_TAGS = re.compile(r"<[^>]+>")
_YEARS = re.compile(r"\s*\([^)]*\)\s*$")
_SEASONS = re.compile(r"^(.*?)\s+seasons?\s+(.+)$", re.IGNORECASE)
_PHASE_LABEL = re.compile(r"^Marvel Cinematic Universe (Phase \w+)$")


def phase_headings(sections):
    """Level-2 headings under the level-1 Films / Television sections of a phase article."""
    headings, inside = [], False
    for s in sections:
        if s["toclevel"] == 1:
            inside = s["line"].startswith(PHASE_SECTIONS)
        elif s["toclevel"] == 2 and inside:
            headings.append(s["line"])
    return headings


def _parse_heading(heading):
    """(normalized name, season numbers or None) of a heading like '<i>Loki</i> season 1 (2021)'."""
    text = _YEARS.sub("", html.unescape(_TAGS.sub("", heading))).strip()
    match = _SEASONS.match(text)
    if match:
        return normalize_name(match.group(1)), {int(n) for n in re.findall(r"\d+", match.group(2))}
    return normalize_name(text), None


def title_scope(title):
    """(normalized name, season numbers or None) of a tier-list title."""
    if title["type"] == SEASON:
        name = title["title"].rsplit(", season", 1)[0]
        return normalize_name(name), {int(title["season_number"])}
    seasons = {int(s) for s in title.get("seasons", "").split("|") if s}
    return normalize_name(title["title"]), seasons or None


def titles_in_heading(heading, titles):
    """QIDs of the Tier 1 titles a phase-article heading is about."""
    name, heading_seasons = _parse_heading(heading)
    found = []
    for t in titles:
        title_name, title_seasons = title_scope(t)
        if title_name != name:
            continue
        if title_seasons is None or heading_seasons is None or title_seasons & heading_seasons:
            if not (t["type"] == SEASON and heading_seasons is None):
                found.append(t["wikidata_qid"])
    return found


def phase_name(item_label):
    match = _PHASE_LABEL.match(item_label or "")
    return match.group(1) if match else ""


def wikidata_phases(entity, labels):
    """(phases, sagas) a title is part of (P179), from the labels of the series items."""
    parts = [labels.get(q, "") for q in claim_values(entity, P_PART_OF_THE_SERIES)]
    return ([p for p in map(phase_name, parts) if p],
            [s for s in parts if s.endswith(" Saga")])


def main():
    retrieved_at = utc_now()
    titles = read_csv(REGISTRY_PATH)
    entities = read_json(ENTITIES_PATH)["entities"]
    wikimedia = WikimediaClient()

    rows = []
    for phase in PHASES:
        parsed = wikimedia.sections(PHASE_ARTICLE.format(phase=phase))
        headings = phase_headings(parsed["sections"])
        url = enwiki_url(parsed["title"])
        write_json(PHASE_PAGES_DIR / f"{phase}.json",
                   {"phase": phase, "page": parsed["title"], "revid": parsed["revid"], "url": url,
                    "headings": headings, "source": "wikipedia", "retrieved_at": retrieved_at,
                    "license": WIKIPEDIA_LICENSE})
        rows += [{"title_qid": q, "phase": phase, "heading": h, "source": "wikipedia",
                  "source_url": url, "revid": parsed["revid"], "retrieved_at": retrieved_at,
                  "license": WIKIPEDIA_LICENSE}
                 for h in headings for q in titles_in_heading(h, titles)]
    write_csv(WIKIPEDIA_PHASES_PATH, rows)

    series = list(dict.fromkeys(q for t in titles for q in
                                claim_values(entities[t["wikidata_qid"]], P_PART_OF_THE_SERIES)))
    labels = {q: label(e) or "" for q, e in wikimedia.get_entities(series, props="labels").items()}
    wikidata_rows = []
    for t in titles:
        phases, sagas = wikidata_phases(entities[t["wikidata_qid"]], labels)
        wikidata_rows.append({"title_qid": t["wikidata_qid"], "title": t["title"],
                              "phases": "|".join(phases), "sagas": "|".join(sagas), "source": "wikidata",
                              "source_url": f"https://www.wikidata.org/wiki/{t['wikidata_qid']}",
                              "retrieved_at": retrieved_at, "license": WIKIDATA_LICENSE})
    write_csv(WIKIDATA_PHASES_PATH, wikidata_rows)
    print(f"Wikipedia: {len(rows)} title-phase rows; Wikidata: phases for "
          f"{sum(bool(r['phases']) for r in wikidata_rows)} titles")


if __name__ == "__main__":
    main()
