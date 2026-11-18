"""Apply the MCU expert's curated roles (docs/data_sources_and_tiers.md, "Curated roles").

A row matches the performances of one actor in one title (or every title, '*'). It can set
the role's identity, reality, display name and the character it is a variant of; blank
cells keep what the data says.
"""

from src.source_data_collection.cast_matching import normalize_name
from src.source_data_collection.tier_titles import TIERS_DOC_PATH, read_table

CURATED_HEADING = "### Curated roles"
ALL_TITLES = "*"
UNKNOWN_REALITY = "Unknown"


def load_curated_roles(path=TIERS_DOC_PATH):
    return read_table(path, CURATED_HEADING)


def _matches(row, performance, title_qids):
    in_title = row["title"] == ALL_TITLES or title_qids.get(row["title"]) == performance["title_qid"]
    return in_title and normalize_name(row["actor"]) == normalize_name(performance["actor_name"])


def apply_curated_roles(performances, rows, title_qids, title_realities):
    """Performances with curated rows applied; each gains curated / curated_label /
    curated_variant_of. `title_qids` maps tier-list titles to QIDs."""
    result = []
    for p in performances:
        row = next((r for r in rows if _matches(r, p, title_qids)), None)
        p = {**p, "curated": False, "curated_label": "", "curated_variant_of": "",
             # the character the data linked, before any merge or curation
             "data_base_qid": p.get("data_base_qid") or p["base_qid"]}
        if row and (p["character_id"] or row["identity"]):
            identity = row["identity"] or p["base_qid"]
            current = p["character_id"].rsplit("@", 1)[1] if p["character_id"] else \
                title_realities[p["title_qid"]]
            p.update(base_qid=identity, character_id=f"{identity}@{row['reality'] or current}",
                     curated=True, curated_label=row["character"],
                     curated_variant_of=row["variant of"])
        result.append(p)
    return result


def unmatched_rows(performances, rows, title_qids):
    """Curated rows that match no performance (e.g. a misspelt actor or title)."""
    return [r for r in rows if not any(_matches(r, p, title_qids) for p in performances)]
