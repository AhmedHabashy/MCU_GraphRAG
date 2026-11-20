"""Build title-level tables: each Tier 1 title's first release and release order, and its
MCU phases and sagas.

The first release is the earliest release of any kind (premieres included) known to either
source: TMDB records premieres that Wikidata often lacks, and occasionally the other way round.
A date verified by hand (docs, "Verified first releases") replaces both.
A title's phases are those named by Wikipedia's phase articles or Wikidata (validation checks
that they agree); its sagas follow from the curated phase -> saga table in the docs.

Needs:  collect_title_details, collect_phases
Output: processed_data/titles/release_order.csv
        processed_data/titles/title_phases.csv
Run:    .venv\\Scripts\\python.exe -m src.processing.build_titles
"""

from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.collect_phases import (
    PHASES, WIKIDATA_PHASES_PATH, WIKIPEDIA_PHASES_PATH,
)
from src.source_data_collection.collect_title_details import (
    TITLE_DETAILS_PATH, TMDB_FIRST_RELEASES_PATH,
)
from src.source_data_collection.collect_timeline import (
    VIEWING_TIMELINE_PATH, WIKIPEDIA_TIMELINE_PATH, years_of,
)
from src.source_data_collection.storage import read_csv, write_csv
from src.source_data_collection.tier_titles import PROJECT_ROOT, TIERS_DOC_PATH, read_table

TITLES_DIR = PROJECT_ROOT / "processed_data" / "titles"
RELEASE_ORDER_PATH = TITLES_DIR / "release_order.csv"
TITLE_PHASES_PATH = TITLES_DIR / "title_phases.csv"
TIMELINE_PATH = TITLES_DIR / "timeline.csv"
PHASES_HEADING = "### Phases and sagas"
VERIFIED_RELEASES_HEADING = "### Verified first releases"


def load_phase_sagas(path=TIERS_DOC_PATH):
    """Curated phase -> saga mapping."""
    return {r["phase"]: r["saga"] for r in read_table(path, PHASES_HEADING)}


def load_verified_releases(title_qids, path=TIERS_DOC_PATH):
    """Title QID -> first release date verified by hand. `title_qids` maps tier-list titles to QIDs."""
    return {title_qids[r["title"]]: r["first release"] for r in read_table(path, VERIFIED_RELEASES_HEADING)}


def first_releases(wikidata_details, tmdb_dates, verified=None):
    """Earliest first release per title from Wikidata and TMDB, naming the source(s); a
    verified date replaces them."""
    rows = []
    for d in wikidata_details:
        if d["title_qid"] in (verified or {}):
            rows.append({"title_qid": d["title_qid"], "title": d["title"],
                         "first_release_date": verified[d["title_qid"]], "first_release_source": "verified"})
            continue
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


def title_phase_rows(titles, wikipedia_rows, wikidata_phases, phase_sagas):
    """Phases (in MCU order) from Wikipedia's current phase articles, else from Wikidata (which
    can keep a title's old planned phase, e.g. Ironheart), their sagas, and the agreeing sources."""
    rows = []
    for t in titles:
        qid = t["wikidata_qid"]
        from_wikipedia = {r["phase"] for r in wikipedia_rows if r["title_qid"] == qid}
        from_wikidata = {p for p in wikidata_phases.get(qid, "").split("|") if p}
        chosen = from_wikipedia or from_wikidata
        phases = [p for p in PHASES if p in chosen]
        sources = [s for s, found in (("wikipedia", from_wikipedia), ("wikidata", from_wikidata))
                   if found and found == chosen]
        rows.append({"title_qid": qid, "title": t["title"], "phases": "|".join(phases),
                     "sagas": "|".join(dict.fromkeys(phase_sagas[p] for p in phases)),
                     "phase_sources": "|".join(sources), "source": "derived"})
    return rows


def _span(years):
    known = [y for y in years if y is not None]
    return (min(known), max(known)) if known else ("", "")


def timeline_rows(titles, viewing_rows, wikipedia_rows):
    """Chronological order (by a title's first row in the MCU wiki viewing timeline) and the
    in-universe years each source gives; titles in neither source are left blank."""
    first_position, mcu_years, wikipedia_years = {}, {}, {}
    for r in viewing_rows:
        if r["title_qid"]:
            first_position.setdefault(r["title_qid"], int(r["position"]))
            mcu_years.setdefault(r["title_qid"], []).extend(years_of(r["dates"]))
    for r in wikipedia_rows:
        if r["title_qid"] and r["start_year"]:
            wikipedia_years.setdefault(r["title_qid"], []).extend([int(r["start_year"]), int(r["end_year"])])
    order = {q: i for i, q in enumerate(sorted(first_position, key=first_position.get), 1)}
    rows = []
    for t in titles:
        q = t["wikidata_qid"]
        mcu_start, mcu_end = _span(mcu_years.get(q, []))
        wp_start, wp_end = _span(wikipedia_years.get(q, []))
        rows.append({"title_qid": q, "title": t["title"], "chronological_order": order.get(q, ""),
                     "mcu_wiki_start_year": mcu_start, "mcu_wiki_end_year": mcu_end,
                     "wikipedia_start_year": wp_start, "wikipedia_end_year": wp_end, "source": "derived"})
    return rows


def main():
    tmdb = {r["title_qid"]: r["first_release_date"] for r in read_csv(TMDB_FIRST_RELEASES_PATH)}
    title_qids = {t["title"]: t["wikidata_qid"] for t in read_csv(REGISTRY_PATH)}
    order = release_order_rows(first_releases(read_csv(TITLE_DETAILS_PATH), tmdb,
                                              load_verified_releases(title_qids)))
    write_csv(RELEASE_ORDER_PATH, order)

    wikidata = {r["title_qid"]: r["phases"] for r in read_csv(WIKIDATA_PHASES_PATH)}
    phases = title_phase_rows(read_csv(REGISTRY_PATH), read_csv(WIKIPEDIA_PHASES_PATH), wikidata,
                              load_phase_sagas())
    write_csv(TITLE_PHASES_PATH, phases)

    timeline = timeline_rows(read_csv(REGISTRY_PATH), read_csv(VIEWING_TIMELINE_PATH),
                             read_csv(WIKIPEDIA_TIMELINE_PATH))
    write_csv(TIMELINE_PATH, timeline)
    print(f"Release order for {len(order)} titles; phases for "
          f"{sum(bool(r['phases']) for r in phases)} titles; chronological order for "
          f"{sum(r['chronological_order'] != '' for r in timeline)} titles")


if __name__ == "__main__":
    main()
