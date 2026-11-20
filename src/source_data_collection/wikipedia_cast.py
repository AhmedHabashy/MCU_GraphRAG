"""Collect the Cast section of each Tier 1 Wikipedia article.

Output: source_data/wikipedia/cast_sections/<title QID>.json (section wikitext, as collected)
"""

from src.source_data_collection.incremental import TitleScopes
from src.source_data_collection.storage import write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.utils import enwiki_url

CAST_SECTIONS_DIR = PROJECT_ROOT / "source_data" / "wikipedia" / "cast_sections"
WIKIPEDIA_LICENSE = "CC BY-SA 4.0"
CAST_HEADING_PREFIX = "Cast"  # matches "Cast" and "Cast and characters"


def cast_section_path(title_qid):
    return CAST_SECTIONS_DIR / f"{title_qid}.json"


def collect(titles, client, retrieved_at):
    """Cast sections of new or changed titles; returns the titles that have none."""
    scopes = TitleScopes("wikipedia_cast")
    for title in scopes.to_collect(titles):
        path = cast_section_path(title["wikidata_qid"])
        section = client.top_level_section(title["enwiki_title"], prefix=CAST_HEADING_PREFIX)
        if section is None:
            path.unlink(missing_ok=True)   # an older section no longer applies
            continue
        write_json(path, {**section, "title": title["title"], "source": "wikipedia",
                          "source_url": enwiki_url(section["page"]),
                          "retrieved_at": retrieved_at, "license": WIKIPEDIA_LICENSE})
    scopes.save(titles)
    return [t["title"] for t in titles if not cast_section_path(t["wikidata_qid"]).exists()]
