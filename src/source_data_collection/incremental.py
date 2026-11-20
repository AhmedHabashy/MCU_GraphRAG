"""Incremental collection: fetch only what is new or changed, keep what was collected.

A title-based collector records, per title, the scope it collected the title for: the
registry fields that decide what is fetched. A title is collected again only when it is new
or its scope changed (Jessica Jones gaining season 3); otherwise its stored rows are kept,
with their original provenance. Units with fixed keys (people, credits, wiki pages) are
simply kept when already stored.

State: source_data/collection_scopes/<collector>.json  ({title QID: scope})
"""

from src.source_data_collection.storage import read_csv, read_json, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT

SCOPES_DIR = PROJECT_ROOT / "source_data" / "collection_scopes"
SCOPE_FIELDS = ("wikidata_qid", "title", "type", "enwiki_title", "seasons", "season_number",
                "tmdb_movie_id", "tmdb_tv_id")


def collection_scope(title):
    return {field: title.get(field, "") for field in SCOPE_FIELDS}


class TitleScopes:
    """The scope each title was last collected for, by one collector."""

    def __init__(self, collector, scopes_dir=SCOPES_DIR):
        self.path = scopes_dir / f"{collector}.json"
        self.collected = read_json(self.path) if self.path.exists() else {}

    def to_collect(self, titles):
        """Titles that are new, or whose scope changed since they were collected."""
        return [t for t in titles if self.collected.get(t["wikidata_qid"]) != collection_scope(t)]

    def save(self, titles):
        """Record `titles` (all titles now in scope) as collected; others are forgotten."""
        self.collected = {t["wikidata_qid"]: collection_scope(t) for t in titles}
        write_json(self.path, self.collected)


def stored_rows(path, keep, key="title_qid"):
    """Rows of the CSV at `path` whose `key` is in `keep` ([] when nothing is stored yet)."""
    return [r for r in read_csv(path) if r[key] in keep] if path.exists() else []


def in_title_order(rows, titles):
    """Rows sorted by their title's position in `titles` (stable within a title)."""
    position = {t["wikidata_qid"]: i for i, t in enumerate(titles)}
    return sorted(rows, key=lambda r: position[r["title_qid"]])


def saved_or_fetched(path, fetch):
    """The page saved at `path` by an earlier run, else `fetch()`ed now and saved there.
    A page that does not exist (fetch gives None) is not saved, so it is tried again next run."""
    if path.exists():
        return read_json(path)
    page = fetch()
    if page is not None:
        write_json(path, page)
    return page
