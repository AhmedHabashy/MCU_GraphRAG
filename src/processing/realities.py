"""Reality names used in the graph, and how they map to Marvel Database Earth pages.

The main MCU universe is Earth-616 (as the films call it). The Marvel Database names its
page "Earth-199999" and keeps "Earth-616" for the comics, which are out of scope for now.
"""

from src.source_data_collection.collect_characters import (
    MARVEL_DB_COMICS_EARTH as MARVEL_DB_COMICS_PAGE,
)

MCU = "Earth-616"
MARVEL_DB_MCU_PAGE = "Earth-199999"


def reality_of_marvel_db_earth(earth):
    """Graph reality for a Marvel Database Earth page name; '' for the comics."""
    if earth == MARVEL_DB_MCU_PAGE:
        return MCU
    if earth == MARVEL_DB_COMICS_PAGE:
        return ""
    return earth


def marvel_db_page_of(reality):
    """Marvel Database Earth page name for a graph reality."""
    return MARVEL_DB_MCU_PAGE if reality == MCU else reality
