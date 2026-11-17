"""Read the title tiers from docs/data_sources_and_tiers.md (the single source of truth for scope)."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TIERS_DOC_PATH = PROJECT_ROOT / "docs" / "data_sources_and_tiers.md"

_SEASON = re.compile(r", season \d+$")
_ADDED = " (added)"
_REVIEW = "†"  # marks curated values the MCU expert should review


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _unescape(text):
    return re.sub(r"\\(.)", r"\1", text)


def _parse_row(header, cells):
    """Columns by header name; Title/Type/Year/Universe required, others (Reality) optional.

    A cell ending in the review marker '†' is stored without it and flags the row.
    """
    needs_review = any(c.endswith(_REVIEW) for c in cells)
    row = {name.lower(): _unescape(cell.removesuffix(_REVIEW).strip())
           for name, cell in zip(header, cells)}
    title = row.pop("title").removesuffix(_ADDED)
    kind = row.pop("type")
    if _SEASON.search(title):
        kind = "Series season"  # listed as "Series"; a season is its own Wikidata class
    year = int(re.match(r"\d{4}", row.pop("year")).group())
    return {"title": title, "type": kind, "year": year, **row, "needs_review": needs_review}


def load_tier_titles(path=TIERS_DOC_PATH, tier=1):
    """Rows of the '### Tier N' table as {title, type, year, universe[, reality]}."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    heading = f"### Tier {tier}:"
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    except StopIteration:
        raise ValueError(f"No '{heading}' section in {path}") from None

    rows, in_table = [], False
    for line in lines[start + 1:]:
        if line.startswith("|"):
            in_table = True
            rows.append(_cells(line))
        elif in_table or line.startswith("#"):
            break
    return [_parse_row(rows[0], cells) for cells in rows[2:]]  # skip header + separator
