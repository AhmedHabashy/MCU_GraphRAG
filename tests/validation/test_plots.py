"""Validation of plot and episode summaries (Wikipedia, cross-checked with Wikidata and TMDB).

Run after collection:  .venv\\Scripts\\python.exe -m pytest -m validation
Collect with:          .venv\\Scripts\\python.exe -m src.source_data_collection.collect_plots
"""

import re

import pytest

from src.source_data_collection.build_title_registry import ENTITIES_PATH, REGISTRY_PATH
from src.source_data_collection.cast_matching import distinctive_tokens, normalize_name
from src.source_data_collection.collect_plots import EPISODE_ENTITIES_PATH, plot_path
from src.source_data_collection.storage import read_csv, read_json
from src.source_data_collection.tmdb_cast import TMDB_CAST_PATH
from src.title_types import MOVIE_TYPES
from src.utils import WikimediaClient, claim_values, label

pytestmark = pytest.mark.validation

Q_FILM, Q_FILM_PROJECT = "Q11424", "Q18011172"
P_NUMBER_OF_EPISODES = "P1113"
P_NUMBER_OF_SEASONS = "P2437"
P_PUBLICATION_DATE = "P577"

PLOT_WORDS = (200, 1500)       # Wikipedia's film plot guideline is 400-700 words
MIN_PREMISE_WORDS = 15
MIN_EPISODE_SUMMARY_WORDS = 30
TOP_CHARACTERS = 5             # top-billed TMDB characters expected in the text
MIN_TOP_CHARACTERS_MENTIONED = 0.6
MIN_WIKIDATA_EPISODES_MATCHED = 0.8
MARKUP_LEFTOVERS = ("[[", "]]", "{{", "}}", "<ref", "&nbsp;", "''")


@pytest.fixture(scope="module")
def titles():
    if not REGISTRY_PATH.exists():
        pytest.skip("registry not collected yet; run build_title_registry")
    return read_csv(REGISTRY_PATH)


@pytest.fixture(scope="module")
def plots(titles):
    missing = [t["title"] for t in titles if not plot_path(t["wikidata_qid"]).exists()]
    if len(missing) == len(titles):
        pytest.skip("plots not collected yet; run src.source_data_collection.collect_plots")
    assert missing == []
    return {t["wikidata_qid"]: read_json(plot_path(t["wikidata_qid"])) for t in titles}


@pytest.fixture(scope="module")
def title_entities():
    return read_json(ENTITIES_PATH)["entities"]


@pytest.fixture(scope="module")
def wikidata_episodes(plots):
    return read_json(EPISODE_ENTITIES_PATH)["by_title"]


def expected_kind(title):
    if title["type"] not in MOVIE_TYPES:
        return "episodes"
    return "premise" if Q_FILM_PROJECT in title["instance_of"].split("|") else "plot"


def words(text):
    return len(text.split())


def full_text(record):
    return record["text"] or "\n".join(e["summary_text"] for e in record["episodes"])


# --- Every title has the right kind of text -------------------------------------------

def test_every_title_has_the_expected_kind_of_text(titles, plots):
    assert [(t["title"], plots[t["wikidata_qid"]]["kind"], expected_kind(t)) for t in titles
            if plots[t["wikidata_qid"]]["kind"] != expected_kind(t)] == []


def test_film_plots_have_a_plausible_length(titles, plots):
    low, high = PLOT_WORDS
    assert [(t["title"], words(plots[t["wikidata_qid"]]["text"])) for t in titles
            if expected_kind(t) == "plot"
            and not low <= words(plots[t["wikidata_qid"]]["text"]) <= high] == []


def test_premises_are_not_empty(titles, plots):
    assert [t["title"] for t in titles if expected_kind(t) == "premise"
            and words(plots[t["wikidata_qid"]]["text"]) < MIN_PREMISE_WORDS] == []


# --- Episodes: complete, numbered, and agreeing with Wikidata -----------------------------

def expected_episode_count(title_qid, title_entities, wikidata_episodes, titles=None):
    """Wikidata's episode count (P1113). For a series limited to only some of its seasons
    (fewer than its number of seasons, P2437), the Wikidata episodes in those seasons."""
    entity = title_entities[title_qid]
    limit = titles and next(t["seasons"] for t in titles if t["wikidata_qid"] == title_qid)
    seasons = claim_values(entity, P_NUMBER_OF_SEASONS)
    partial = limit and (not seasons or len(limit.split("|")) < int(seasons[0]["amount"]))
    counts = claim_values(entity, P_NUMBER_OF_EPISODES)
    if counts and not partial:
        return int(counts[0]["amount"])
    return len(wikidata_episodes[title_qid])


def aired(record):
    """Episodes that have aired; announced ones (no full or a future air date) are left out."""
    return [e for e in record["episodes"] if e["aired"]]


def test_episode_counts_match_wikidata(titles, plots, title_entities, wikidata_episodes):
    expected = {t["wikidata_qid"]: expected_episode_count(t["wikidata_qid"], title_entities,
                                                          wikidata_episodes, titles) for t in titles
                if expected_kind(t) == "episodes"}
    assert [(t["title"], len(aired(plots[q])), expected[q]) for t in titles
            if (q := t["wikidata_qid"]) in expected and len(aired(plots[q])) != expected[q]] == []


def test_what_if_has_only_seasons_one_and_two(plots):
    episodes = plots["Q65980671"]["episodes"]
    assert {e["season"] for e in episodes} == {1, 2} and len(episodes) == 18


def test_episodes_are_numbered_one_to_n_within_each_season(plots):
    bad = []
    for record in plots.values():
        seasons = {}
        for e in aired(record):
            seasons.setdefault(e["season"], []).append(e["number_in_season"])
        bad += [(record["title"], s, n) for s, n in seasons.items()
                if sorted(n) != list(range(1, len(n) + 1))]
    assert bad == []


def test_every_episode_has_title_air_date_and_summary(plots):
    assert [(r["title"], e["season"], e["number_in_season"]) for r in plots.values()
            for e in aired(r)
            if not (e["title"] and e["air_date"]
                    and words(e["summary_text"]) >= MIN_EPISODE_SUMMARY_WORDS)] == []


def test_episode_titles_and_air_dates_agree_with_wikidata(plots, wikidata_episodes):
    """Match Wikipedia episodes to Wikidata episode items by title, then compare air dates."""
    unmatched, wrong_date = [], []
    for title_qid, items in wikidata_episodes.items():
        by_title = {normalize_name(e["title"]): e for e in plots[title_qid]["episodes"]}
        for item in items:
            episode = by_title.get(normalize_name(label(item) or ""))
            if episode is None:
                unmatched.append((plots[title_qid]["title"], label(item)))
                continue
            dates = {d["time"][1:11] for d in claim_values(item, P_PUBLICATION_DATE)}
            if dates and episode["air_date"] not in dates:
                wrong_date.append((label(item), episode["air_date"], sorted(dates)))
    total = sum(len(v) for v in wikidata_episodes.values())
    assert total and 1 - len(unmatched) / total >= MIN_WIKIDATA_EPISODES_MATCHED, unmatched
    assert wrong_date == []


# --- Text quality and cross-source sense check -----------------------------------------

def test_plain_text_has_no_markup_leftovers(plots):
    texts = [(r["title"], r["text"]) for r in plots.values()] + \
            [(r["title"], e["summary_text"]) for r in plots.values() for e in r["episodes"]]
    assert [(title, m) for title, text in texts for m in MARKUP_LEFTOVERS if m in text] == []


def test_top_billed_characters_appear_in_the_text(titles, plots):
    """The main TMDB characters should be named in the plot (or episode summaries)."""
    cast = read_csv(TMDB_CAST_PATH)
    low = []
    for t in titles:
        if expected_kind(t) == "premise":
            continue
        text_words = set(normalize_name(full_text(plots[t["wikidata_qid"]])).split())
        top = sorted((r for r in cast if r["title_qid"] == t["wikidata_qid"]),
                     key=lambda r: int(r["billing_order"]))
        characters = [tokens for r in top if (tokens := distinctive_tokens(r["character"]))]
        characters = characters[:TOP_CHARACTERS]
        mentioned = sum(bool(tokens & text_words) for tokens in characters)
        if mentioned / len(characters) < MIN_TOP_CHARACTERS_MENTIONED:
            low.append((t["title"], f"{mentioned}/{len(characters)}"))
    assert low == []


# --- Provenance ------------------------------------------------------------------------

def test_every_section_records_page_revision_url_and_license(plots):
    assert [r["title"] for r in plots.values()
            if r["license"] != "CC BY-SA 4.0" or not r["retrieved_at"] or not r["sections"]
            or not all(s["revid"] and s["url"] and s["page"] for s in r["sections"])] == []


def test_episode_count_property_id_has_expected_label():
    entities = WikimediaClient().get_entities([P_NUMBER_OF_EPISODES], props="labels")
    assert label(entities[P_NUMBER_OF_EPISODES]) == "number of episodes"


def test_episode_numbers_are_unique_per_title(plots):
    """Aired episodes only: announced specials (Marvel Zombies) restart their own numbering."""
    dupes = []
    for r in plots.values():
        keys = [(e["season"], e["number_in_season"]) for e in aired(r)]
        dupes += [(r["title"], k) for k in set(keys) if keys.count(k) > 1]
    assert dupes == []


def test_season_titles_match_their_page(plots, titles):
    """A season row must only contain that season's episodes."""
    seasons = [t for t in titles if t["type"] == "Series season"]
    assert [t["title"] for t in seasons
            if {e["season"] for e in plots[t["wikidata_qid"]]["episodes"]}
            != {int(re.search(r"season (\d+)$", t["title"]).group(1))}] == []
