"""Validation of MCU phases and sagas: Wikipedia phase articles vs Wikidata vs the docs.

Run after collection:  .venv\\Scripts\\python.exe -m pytest -m validation
Collect with:          .venv\\Scripts\\python.exe -m src.source_data_collection.collect_phases
                       .venv\\Scripts\\python.exe -m src.processing.build_titles
"""

import pytest

from src.processing.build_titles import RELEASE_ORDER_PATH, TITLE_PHASES_PATH, load_phase_sagas
from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.collect_phases import (
    PHASES, WIKIDATA_PHASES_PATH, WIKIPEDIA_PHASES_PATH,
)
from src.source_data_collection.storage import read_csv

pytestmark = pytest.mark.validation

PHASED_UNIVERSES = {"MCU", "MCU animation"}   # Marvel Studios; Marvel TV, Netflix, Fox and Sony have no phases
X_MEN_97 = "Q109558622"
MAX_PHASE_DISAGREEMENT = 0.05


def _load(path):
    if not path.exists():
        pytest.skip(f"{path} not collected yet; run collect_phases and build_titles")
    return read_csv(path)


@pytest.fixture(scope="module")
def titles():
    return {t["wikidata_qid"]: t for t in read_csv(REGISTRY_PATH)}


@pytest.fixture(scope="module")
def phases(titles):
    return {r["title_qid"]: r for r in _load(TITLE_PHASES_PATH)}


def split(value):
    return [v for v in value.split("|") if v]


# --- Coverage -------------------------------------------------------------------------

def _phased(qid, title):
    return title["universe"] in PHASED_UNIVERSES and qid != X_MEN_97


def test_every_marvel_studios_title_has_a_phase(titles, phases):
    assert [t["title"] for q, t in titles.items() if _phased(q, t) and not phases[q]["phases"]] == []


def test_other_studios_titles_and_x_men_97_have_no_phase(titles, phases):
    assert [t["title"] for q, t in titles.items() if not _phased(q, t) and phases[q]["phases"]] == []


# --- Wikipedia vs Wikidata vs docs ------------------------------------------------------

def test_wikipedia_and_wikidata_mostly_agree_where_both_name_a_phase(titles):
    """Wikidata can keep a title's old planned phase (Ironheart: Phase Four, now Phase Five);
    Wikipedia's current phase articles take precedence, so a few disagreements are allowed."""
    wikipedia = {}
    for r in _load(WIKIPEDIA_PHASES_PATH):
        wikipedia.setdefault(r["title_qid"], set()).add(r["phase"])
    wikidata = {r["title_qid"]: set(split(r["phases"])) for r in _load(WIKIDATA_PHASES_PATH)}
    both = [q for q, p in wikidata.items() if p and q in wikipedia]
    disagree = [(titles[q]["title"], sorted(wikipedia[q]), sorted(wikidata[q])) for q in both
                if wikidata[q] != wikipedia[q]]
    assert len(disagree) / len(both) <= MAX_PHASE_DISAGREEMENT, disagree


def test_ironheart_uses_its_current_phase(phases):
    assert phases["Q108124282"]["phases"] == "Phase Five"


def test_curated_sagas_agree_with_wikidata(titles):
    sagas = load_phase_sagas()
    wrong = [(r["title"], r["phases"], r["sagas"]) for r in _load(WIKIDATA_PHASES_PATH)
             if r["phases"] and r["sagas"]
             and {sagas[p] for p in split(r["phases"])} != set(split(r["sagas"]))]
    assert wrong == []


def test_docs_list_six_phases_in_two_sagas():
    sagas = load_phase_sagas()
    assert list(sagas) == PHASES
    assert {p: s for p, s in sagas.items()} == {
        **{p: "The Infinity Saga" for p in PHASES[:3]}, **{p: "The Multiverse Saga" for p in PHASES[3:]}}


# --- Order ------------------------------------------------------------------------------

def test_each_phase_ends_before_the_next_begins(phases):
    """Titles spanning two phases (What If...? seasons 1-2) are left out."""
    dates = {r["title_qid"]: r["first_release_date"] for r in _load(RELEASE_ORDER_PATH)}
    by_phase = {}
    for q, r in phases.items():
        if len(split(r["phases"])) == 1:
            by_phase.setdefault(r["phases"], []).append(dates[q])
    present = [p for p in PHASES if p in by_phase]
    assert [(a, b) for a, b in zip(present, present[1:]) if max(by_phase[a]) >= min(by_phase[b])] == []


# --- Spot checks ------------------------------------------------------------------------

@pytest.mark.parametrize("title_qid, expected_phases, expected_sagas", [
    ("Q192724", "Phase One", "The Infinity Saga"),                     # Iron Man
    ("Q23781155", "Phase Three", "The Infinity Saga"),                 # Avengers: Endgame
    ("Q107185252", "Phase Four", "The Multiverse Saga"),               # Loki, season 1
    ("Q112610403", "Phase Five", "The Multiverse Saga"),               # Loki, season 2
    ("Q65980671", "Phase Four|Phase Five", "The Multiverse Saga"),     # What If...? seasons 1-2
    ("Q102180106", "Phase Five", "The Multiverse Saga"),               # Deadpool & Wolverine
    ("Q113244839", "Phase Six", "The Multiverse Saga"),                # Avengers: Doomsday
])
def test_known_phases(phases, title_qid, expected_phases, expected_sagas):
    assert (phases[title_qid]["phases"], phases[title_qid]["sagas"]) == (expected_phases, expected_sagas)


def test_rows_have_provenance():
    rows = _load(WIKIPEDIA_PHASES_PATH) + _load(WIKIDATA_PHASES_PATH)
    assert [r for r in rows for f in ("source", "source_url", "retrieved_at", "license") if not r[f]] == []
