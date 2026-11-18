"""Collect Tier 1 analytics: box office, budget, runtime, ratings, genres and companies.

TMDB is the main source; Wikidata's box office (P2142), cost (P2130) and duration (P2047)
are collected as a cross-check.

Needs:  build_title_registry
Output: source_data/tmdb/title_details/<title QID>.json  (raw TMDB details, as collected)
        source_data/tmdb/title_stats.csv           (one row per title)
        source_data/wikidata/title_money.csv       (Wikidata figures per title)
Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.collect_title_stats
"""

from statistics import median

from src.source_data_collection.build_title_registry import (
    ENTITIES_PATH, REGISTRY_PATH, SEASON, WIKIDATA_LICENSE,
)
from src.source_data_collection.storage import read_csv, read_json, utc_now, write_csv, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.source_data_collection.tmdb_cast import TMDB_LICENSE, make_client
from src.tmdb_client import TMDB_API
from src.title_types import is_movie
from src.utils import quantities

TMDB_DIR = PROJECT_ROOT / "source_data" / "tmdb"
TMDB_DETAILS_DIR = TMDB_DIR / "title_details"
TMDB_STATS_PATH = TMDB_DIR / "title_stats.csv"
WIKIDATA_MONEY_PATH = PROJECT_ROOT / "source_data" / "wikidata" / "title_money.csv"

# Wikidata property and unit IDs (verified on wikidata.org, see validation).
P_BOX_OFFICE = "P2142"
P_COST = "P2130"   # labelled "capital cost"; film items use it for the production budget
P_DURATION = "P2047"
Q_US_DOLLAR = "Q4917"
Q_MINUTE = "Q7727"


def _blank_if_zero(value):
    return value if value else ""


def _names(items):
    return "|".join(i["name"] for i in items or [])


def tmdb_stats_row(title, path, payload, series_genres, retrieved_at):
    """One stats row; a season takes its runtime from its episodes and genres from its series."""
    if is_movie(title):
        runtime = payload.get("runtime")
    elif title["type"] == SEASON:
        runtimes = [e["runtime"] for e in payload.get("episodes", []) if e.get("runtime")]
        runtime = round(median(runtimes)) if runtimes else ""
    else:
        runtime = round(median(payload["episode_run_time"])) if payload.get("episode_run_time") else ""
    genres = "|".join(series_genres) if title["type"] == SEASON else _names(payload.get("genres"))
    votes = payload.get("vote_count", "")
    if title["type"] == SEASON:  # seasons have no vote count of their own; their episodes do
        votes = sum(e.get("vote_count") or 0 for e in payload.get("episodes", []))
    return {
        "title": title["title"], "title_qid": title["wikidata_qid"], "type": title["type"],
        "budget_usd": _blank_if_zero(payload.get("budget")),
        "revenue_usd": _blank_if_zero(payload.get("revenue")),
        "runtime_minutes": _blank_if_zero(runtime),
        "vote_average": payload.get("vote_average", ""), "vote_count": votes,
        "popularity": payload.get("popularity", ""),
        "genres": genres, "production_companies": _names(payload.get("production_companies")),
        "source": "tmdb", "source_url": f"{TMDB_API}{path}",
        "retrieved_at": retrieved_at, "license": TMDB_LICENSE,
    }


def _largest(entity, pid, unit):
    amounts = [a for a, u in quantities(entity, pid) if u == unit]
    return round(max(amounts)) if amounts else ""


def wikidata_money_row(title, entity, retrieved_at):
    """Largest US-dollar box office and cost (worldwide is the largest regional figure), and
    the duration in minutes."""
    return {
        "title": title["title"], "title_qid": title["wikidata_qid"],
        "box_office_usd": _largest(entity, P_BOX_OFFICE, Q_US_DOLLAR),
        "cost_usd": _largest(entity, P_COST, Q_US_DOLLAR),
        "duration_minutes": _largest(entity, P_DURATION, Q_MINUTE),
        "source": "wikidata", "source_url": f"https://www.wikidata.org/wiki/{title['wikidata_qid']}",
        "retrieved_at": retrieved_at, "license": WIKIDATA_LICENSE,
    }


def main():
    retrieved_at = utc_now()
    titles = read_csv(REGISTRY_PATH)
    entities = read_json(ENTITIES_PATH)["entities"]
    tmdb = make_client()

    rows = []
    for title in titles:
        path, payload = tmdb.details(title)
        series_genres = []
        if title["type"] == SEASON:
            _, series = tmdb.details({**title, "type": "Series"})
            series_genres = [g["name"] for g in series.get("genres", [])]
        write_json(TMDB_DETAILS_DIR / f"{title['wikidata_qid']}.json",
                   {"title": title["title"], "source_url": f"{TMDB_API}{path}",
                    "retrieved_at": retrieved_at, "license": TMDB_LICENSE, "response": payload})
        rows.append(tmdb_stats_row(title, path, payload, series_genres, retrieved_at))
    write_csv(TMDB_STATS_PATH, rows)
    write_csv(WIKIDATA_MONEY_PATH, [wikidata_money_row(t, entities[t["wikidata_qid"]], retrieved_at)
                                    for t in titles])
    print(f"Stats for {len(rows)} titles; box office known for "
          f"{sum(bool(r['revenue_usd']) for r in rows)}")


if __name__ == "__main__":
    main()
