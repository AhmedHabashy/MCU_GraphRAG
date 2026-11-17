"""Unit tests for src/source_data_collection/cast_matching.py."""

import pytest

from src.source_data_collection.cast_matching import (
    character_flags,
    character_matches,
    distinctive_tokens,
    normalize_name,
)


# --- normalize_name -----------------------------------------------------------

def test_normalize_name_folds_case_accents_and_punctuation():
    assert normalize_name("Zoë Saldaña") == "zoe saldana"
    assert normalize_name("Robert Downey Jr.") == "robert downey jr"


def test_normalize_name_collapses_wiki_markup_and_spaces():
    assert normalize_name("[[Robert Downey Jr.|Downey]]  as  ''Tony''") == \
        "robert downey jr downey as tony"


# --- character_flags ----------------------------------------------------------

def test_character_flags_reads_tmdb_annotations():
    assert character_flags("The Watcher (voice)") == {
        "is_voice": True, "is_uncredited": False, "is_archive": False}
    assert character_flags("Peggy Carter (archive footage) (uncredited)") == {
        "is_voice": False, "is_uncredited": True, "is_archive": True}


def test_character_flags_are_false_for_plain_names():
    assert character_flags("Tony Stark") == {
        "is_voice": False, "is_uncredited": False, "is_archive": False}


# --- character_matches --------------------------------------------------------

@pytest.mark.parametrize("tmdb_character, wikidata_names", [
    ("Tony Stark", ["Iron Man", "Tony Stark"]),                 # exact alias
    ("Victor von Doom  / Doctor Doom", ["Doctor Doom"]),        # one of several "/" parts
    ("Thor", ["Thor Odinson"]),                                 # name contained in the other
    ("Steve Rogers / Captain America", ["Steven Rogers"]),      # shared distinctive surname
    ("The Watcher (voice)", ["The Watcher"]),                   # annotation ignored
])
def test_character_matches_equivalent_names(tmdb_character, wikidata_names):
    assert character_matches(tmdb_character, wikidata_names)


def test_distinctive_tokens_drop_annotations_and_generic_words():
    assert distinctive_tokens("Victor von Doom  / Doctor Doom (voice)") == {"victor", "doom"}
    assert distinctive_tokens("Additional Voices (voice)") == set()
    assert distinctive_tokens("Agent Coulson") == {"coulson"}


@pytest.mark.parametrize("tmdb_character, wikidata_names", [
    ("Tony Stark", ["Pepper Potts"]),
    ("Agent Coulson", ["Agent Carter"]),     # shares only a generic word
    ("Young Man", ["Old Man"]),
    ("", ["Loki"]),
])
def test_character_matches_rejects_different_characters(tmdb_character, wikidata_names):
    assert not character_matches(tmdb_character, wikidata_names)
