"""Collect Tier 1 cast from TMDB, Wikidata and Wikipedia (for cross-source validation).

Needs: source_data/wikidata/tier1_titles.csv (run build_title_registry first)
       TMDB_API_KEY in .env
Run:   .venv\\Scripts\\python.exe -m src.source_data_collection.collect_cast
"""

from src.source_data_collection import tmdb_cast, wikidata_cast, wikipedia_cast
from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.storage import read_csv, utc_now
from src.utils import WikimediaClient


def main():
    titles = read_csv(REGISTRY_PATH)
    retrieved_at = utc_now()
    wikimedia = WikimediaClient()
    tmdb = tmdb_cast.make_client()

    tmdb_rows = tmdb_cast.collect(titles, tmdb, retrieved_at)
    print(f"TMDB: {len(tmdb_rows)} credits for {len(titles)} titles", flush=True)

    person_ids = list(dict.fromkeys(r["tmdb_person_id"] for r in tmdb_rows))
    wikidata_rows, mapping = wikidata_cast.collect(titles, person_ids, wikimedia, retrieved_at)
    print(f"Wikidata: {len(wikidata_rows)} cast pairs; {len(mapping)} TMDB<->QID links",
          flush=True)

    # TMDB's own Wikidata pointer: cross-checks the main cast and settles ambiguous links.
    ambiguous = wikidata_cast.ambiguous_person_ids(mapping)
    checked = list(dict.fromkeys(tmdb_cast.top_billed_person_ids(tmdb_rows) + ambiguous))
    tmdb_cast.collect_external_ids(checked, tmdb, retrieved_at)
    print(f"TMDB external IDs: {len(checked)} people ({len(ambiguous)} ambiguous)", flush=True)

    missing = wikipedia_cast.collect(titles, wikimedia, retrieved_at)
    print(f"Wikipedia: cast sections for {len(titles) - len(missing)} titles; "
          f"missing: {missing}", flush=True)


if __name__ == "__main__":
    main()
