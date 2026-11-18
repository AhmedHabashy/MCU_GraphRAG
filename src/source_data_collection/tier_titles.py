"""Read curated tables from docs/data_sources_and_tiers.md, the single source of truth for scope:
the title tiers, and other curated tables (e.g. curated roles)."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TIERS_DOC_PATH = PROJECT_ROOT / "docs" / "data_sources_and_tiers.md"

_SEASON = re.compile(r", season \d+$")
_SEASON_RANGE = re.compile(r", seasons (\d+)-(\d+)$")
_ADDED = " (added)"
_REVIEW = "†"  # marks curated values the MCU expert should review


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _unescape(text):
    return re.sub(r"\\(.)", r"\1", text)


def read_table(path, heading):
    """Rows of the first Markdown table after a line starting with `heading`, keyed by the
    lower-cased header. A cell ending in '†' is stored without it and flags the row."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    except StopIteration:
        raise ValueError(f"No '{heading}' section in {path}") from None

    table, in_table = [], False
    for line in lines[start + 1:]:
        if line.startswith("|"):
            in_table = True
            table.append(_cells(line))
        elif in_table or line.startswith("#"):
            break
    header = [h.lower() for h in table[0]] if table else []
    rows = []
    for cells in table[2:]:  # skip header + separator
        rows.append({**{name: _unescape(cell.removesuffix(_REVIEW).strip())
                        for name, cell in zip(header, cells)},
                     "needs_review": any(c.endswith(_REVIEW) for c in cells)})
    return rows


def _title_row(row):
    title = row.pop("title")
    kind = row.pop("type")
    seasons = ""
    match = _SEASON_RANGE.search(title)
    if match:  # "Name, seasons 1-2": the series limited to those seasons
        first, last = int(match.group(1)), int(match.group(2))
        seasons = "|".join(str(n) for n in range(first, last + 1))
        title = title[:match.start()]
    title = title.removesuffix(_ADDED)
    if _SEASON.search(title):
        kind = "Series season"  # listed as "Series"; a season is its own Wikidata class
    year = int(re.match(r"\d{4}", row.pop("year")).group())
    needs_review = row.pop("needs_review")
    return {"title": title, "type": kind, "year": year, **row, "seasons": seasons,
            "needs_review": needs_review}


def load_tier_titles(path=TIERS_DOC_PATH, tier=1):
    """Rows of the '### Tier N' table as {title, type, year, universe[, reality], seasons}."""
    return [_title_row(row) for row in read_table(path, f"### Tier {tier}:")]
