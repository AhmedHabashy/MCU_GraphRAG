"""Read the title tiers from docs/data_sources_and_tiers.md (the single source of truth for scope)."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TIERS_DOC_PATH = PROJECT_ROOT / "docs" / "data_sources_and_tiers.md"

_SEASON = re.compile(r", season \d+$")
_ADDED = " (added)"


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _unescape(text):
    return re.sub(r"\\(.)", r"\1", text)


def _parse_row(cells):
    title, kind, year, universe = (_unescape(c) for c in cells)
    title = title.removesuffix(_ADDED)
    if _SEASON.search(title):
        kind = "Series season"  # listed as "Series"; a season is its own Wikidata class
    return {"title": title, "type": kind,
            "year": int(re.match(r"\d{4}", year).group()), "universe": universe}


def load_tier_titles(path=TIERS_DOC_PATH, tier=1):
    """Rows of the '### Tier N' table as {title, type, year, universe}."""
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
    return [_parse_row(cells) for cells in rows[2:]]  # skip header + separator
