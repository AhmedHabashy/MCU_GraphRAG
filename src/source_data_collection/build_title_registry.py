"""Resolve the Tier 1 titles to Wikipedia articles, Wikidata QIDs and crosswalk IDs.

Input:  Tier 1 table in docs/data_sources_and_tiers.md
Output: source_data/wikidata/tier1_titles.csv    (one row per title)
        source_data/wikidata/tier1_entities.json (raw Wikidata entities, as collected)

TV seasons have no TMDB or IMDb ID of their own, so a season row takes them from its
parent series (P179, with the season number from qualifier P1545). A season item with
no date takes its year from its earliest episode (P527 -> P577).

Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.build_title_registry
"""

from src.source_data_collection.storage import utc_now, write_csv, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT, load_tier_titles
from src.utils import WikimediaClient, claim_values, earliest_year, label, qualifier_value

OUTPUT_DIR = PROJECT_ROOT / "source_data" / "wikidata"
REGISTRY_PATH = OUTPUT_DIR / "tier1_titles.csv"
ENTITIES_PATH = OUTPUT_DIR / "tier1_entities.json"

WIKIDATA_LICENSE = "CC0-1.0"

# Wikidata property IDs (verified on wikidata.org 2026-11-17).
P_INSTANCE_OF = "P31"
P_TMDB_MOVIE_ID = "P4947"
P_TMDB_TV_ID = "P4983"
P_IMDB_ID = "P345"
P_PART_OF_THE_SERIES = "P179"
P_SERIES_ORDINAL = "P1545"
P_HAS_PARTS = "P527"

SEASON = "Series season"

# Wikidata classes accepted for each title type.
ALLOWED_INSTANCE_OF = {
    "Film": {"Q11424",                  # film
             "Q18011172"},              # film project (unreleased, e.g. Avengers: Doomsday)
    "Series": {"Q5398426"},             # television series
    "Animated series": {"Q117467246"},  # animated television series
    SEASON: {"Q3464665"},               # television series season
}


def enwiki_candidates(title):
    """Wikipedia article titles to try, most specific first."""
    name, year, kind = title["title"], title["year"], title["type"]
    if kind == SEASON:
        return [name.replace(", season", " season")]
    if kind == "Film":
        return [f"{name} ({year} film)", f"{name} (film)", name]
    return [f"{name} (TV series)", f"{name} ({year} TV series)", name]


def _matches(title, page, entity):
    if not page["qid"] or page["is_disambiguation"] or page["missing"] or not entity:
        return False
    if not set(claim_values(entity, P_INSTANCE_OF)) & ALLOWED_INSTANCE_OF[title["type"]]:
        return False
    year = earliest_year(entity)
    return year is None or year == title["year"]  # undated items fall back to episodes


def _joined(entity, pid):
    return "|".join(claim_values(entity, pid))


def _year(entity, related):
    """(year, where it came from): the item's own date, else its earliest episode."""
    year = earliest_year(entity)
    if year is not None:
        return year, "item"
    episode_years = [y for q in claim_values(entity, P_HAS_PARTS)
                     if (y := earliest_year(related.get(q, {}))) is not None]
    return (min(episode_years), "episodes") if episode_years else ("", "")


def _row(title, page, entity, related, retrieved_at):
    qid = page["qid"] if page else ""
    parent_qid, season_number = (qualifier_value(entity, P_PART_OF_THE_SERIES, P_SERIES_ORDINAL)
                                 if title["type"] == SEASON else (None, None))
    ids_from = related.get(parent_qid, {}) if parent_qid else entity
    year, year_from = _year(entity, related) if entity else ("", "")
    return {
        **title,
        "enwiki_title": page["resolved_title"] if page else "",
        "wikidata_qid": qid,
        "wikidata_label": (label(entity) if entity else None) or "",
        "wikidata_year": year,
        "instance_of": _joined(entity, P_INSTANCE_OF),
        "tmdb_movie_id": _joined(ids_from, P_TMDB_MOVIE_ID),
        "tmdb_tv_id": _joined(ids_from, P_TMDB_TV_ID),
        "imdb_id": _joined(ids_from, P_IMDB_ID),
        "wikidata_year_from": year_from,
        "parent_series_qid": parent_qid or "",
        "season_number": season_number or "",
        "source": "wikidata",
        "source_url": f"https://www.wikidata.org/wiki/{qid}" if qid else "",
        "retrieved_at": retrieved_at,
        "license": WIKIDATA_LICENSE,
    }


def _related_qids(title, entity):
    """Parent series and (for undated seasons) episode QIDs needed to complete a season row."""
    if title["type"] != SEASON:
        return []
    parent_qid, _ = qualifier_value(entity, P_PART_OF_THE_SERIES, P_SERIES_ORDINAL)
    episodes = claim_values(entity, P_HAS_PARTS) if earliest_year(entity) is None else []
    return ([parent_qid] if parent_qid else []) + episodes


def build_rows(titles, client, retrieved_at):
    """One row per title, using the first candidate article whose entity matches."""
    candidates = {t["title"]: enwiki_candidates(t) for t in titles}
    pages = client.resolve_enwiki_titles(
        list(dict.fromkeys(c for cs in candidates.values() for c in cs)))
    entities = client.get_entities(
        list(dict.fromkeys(p["qid"] for p in pages.values() if p["qid"])))

    selected = []  # (title, matching page or None, its entity or {})
    for title in titles:
        page = next((pages[c] for c in candidates[title["title"]]
                     if _matches(title, pages[c], entities.get(pages[c]["qid"]))), None)
        selected.append((title, page, entities[page["qid"]] if page else {}))

    related = client.get_entities(list(dict.fromkeys(
        q for title, _, entity in selected for q in _related_qids(title, entity))))

    rows = [_row(title, page, entity, related, retrieved_at)
            for title, page, entity in selected]
    kept = {page["qid"]: entity for _, page, entity in selected if page}
    return rows, {**kept, **related}


def main():
    titles = load_tier_titles(tier=1)
    retrieved_at = utc_now()
    rows, entities = build_rows(titles, WikimediaClient(), retrieved_at)

    write_csv(REGISTRY_PATH, rows)
    write_json(ENTITIES_PATH, {"retrieved_at": retrieved_at, "source": "wikidata",
                               "license": WIKIDATA_LICENSE, "entities": entities})

    print(f"Wrote {len(rows)} rows to {REGISTRY_PATH}")
    print(f"Wrote {len(entities)} raw entities to {ENTITIES_PATH}")


if __name__ == "__main__":
    main()
