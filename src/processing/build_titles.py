"""Build each Tier 1 title's first release and the release order of all titles.

The first release is the earliest release of any kind (premieres included) known to either
source: TMDB records premieres that Wikidata often lacks, and occasionally the other way round.

Needs:  collect_title_details (Wikidata details and TMDB first releases)
Output: processed_data/titles/release_order.csv
Run:    .venv\\Scripts\\python.exe -m src.processing.build_titles
"""

from src.source_data_collection.collect_title_details import (
    TITLE_DETAILS_PATH, TMDB_FIRST_RELEASES_PATH,
)
from src.source_data_collection.storage import read_csv, write_csv
from src.source_data_collection.tier_titles import PROJECT_ROOT

RELEASE_ORDER_PATH = PROJECT_ROOT / "processed_data" / "titles" / "release_order.csv"


def first_releases(wikidata_details, tmdb_dates):
    """Earliest first release per title from Wikidata and TMDB, naming the source(s)."""
    rows = []
    for d in wikidata_details:
        dates = {"wikidata": d["first_release_date"], "tmdb": tmdb_dates.get(d["title_qid"], "")}
        earliest = min((v for v in dates.values() if v), default="")
        rows.append({"title_qid": d["title_qid"], "title": d["title"],
                     "first_release_date": earliest,
                     "first_release_source": "|".join(s for s, v in dates.items() if v and v == earliest)})
    return rows


def release_order_rows(titles):
    """1-based release order by first release date (ties by title); undated titles left out."""
    dated = sorted((t for t in titles if t["first_release_date"]),
                   key=lambda t: (t["first_release_date"], t["title"]))
    return [{**t, "release_order": i, "source": "derived"} for i, t in enumerate(dated, 1)]


def main():
    tmdb = {r["title_qid"]: r["first_release_date"] for r in read_csv(TMDB_FIRST_RELEASES_PATH)}
    rows = release_order_rows(first_releases(read_csv(TITLE_DETAILS_PATH), tmdb))
    write_csv(RELEASE_ORDER_PATH, rows)
    print(f"Release order for {len(rows)} titles")


if __name__ == "__main__":
    main()
