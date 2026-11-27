"""Unit tests for the pure parts of src/retrieval/local.py (no database)."""

from src.retrieval.local import (
    CUT, cast_line, character_block, entry_points, fit, fuse, group_title_line, lucene_text, name_spans,
    other_names, person_block, shared_block, shared_name, shares, team_block, title_line,
)


def test_a_cast_entry_gives_each_actors_other_titles_by_character_in_release_order():
    other = {"Charlie Cox": [
        {"title": "Echo", "order": 80, "character": "Matt Murdock", "reality": "Earth-616"},
        {"title": "Your Friendly Neighborhood Spider-Man", "order": 90, "character": "Matt Murdock", "reality": "Earth-86445"},
        {"title": "Spider-Man: No Way Home", "order": 60, "character": "Matt Murdock", "reality": "Earth-616"}]}
    entry = {"label": "Matt Murdock", "reality": "Earth-616", "actors": ["Charlie Cox", "Skylar Gaertner"]}
    assert cast_line(entry, other) == ("- Matt Murdock [Earth-616] (Charlie Cox; also in Spider-Man: No Way Home, Echo; "
                                       "as Matt Murdock [Earth-86445] in Your Friendly Neighborhood Spider-Man | Skylar Gaertner)")
    assert cast_line({"label": "Waiter", "reality": "Earth-616", "actors": []}, other) == "- Waiter [Earth-616]"


def test_a_team_member_shows_the_aliases_that_say_more_than_its_label_and_every_role():
    assert other_names("Alexei Shostakov", ["Alexei", "Alexei Shostakov", "Red Guardian"]) == ["Red Guardian"]
    row = {"name": "New Avengers", "reality": "Earth-616", "kind": "team", "aliases": [], "summary": None,
           "members": [{"label": "Ava Starr", "reality": "Earth-616", "aliases": ["Ava", "Ghost"],
                        "roles": ["member, current", "founder, current"]}]}
    assert team_block(row, []).split("\n")[1:] == [
        "Members (wikis):", "- Ava Starr [Earth-616] (also Ghost): member, current / founder, current"]


def test_a_short_block_leaves_its_unused_share_to_the_others():
    assert shares([10, 500, 500], 310) == [10, 150, 150]
    assert shares([500, 10], 1000) == [500, 10]


def test_a_long_line_is_cut_at_a_sentence_end_not_dropped():
    text = "## Summary\nTony builds a suit. He escapes the cave. He becomes Iron Man and fights Stane."
    assert fit([text], [], max_chars=60) == "## Summary\nTony builds a suit. He escapes the cave.\n[cut]"


def test_a_long_first_block_cannot_push_out_a_later_one():
    first = "## A\n" + "\n".join("a" * 50 for _ in range(40))
    text = fit([first, "## B\nshort"], [], max_chars=500)
    assert text.endswith("## B\nshort") and CUT in text and len(text) <= 500


def test_a_group_title_line_leaves_out_money_and_ratings():
    t = {"title": "Eyes of Wakanda", "qid": "Q2", "type": "Series", "year": 2025, "first_release_date": "2025-08-01",
         "start_year": -1260, "end_year": 1896, "chronological_order": 1, "universe": "MCU animation",
         "phases": ["Phase Five"], "box_office_usd": None, "tmdb_rating": 6.9}
    assert group_title_line(t) == ("Eyes of Wakanda [Q2] (Series, released 2025-08-01; set -1260 to 1896, "
                                   "in-universe order 1; universe MCU animation; phases: Phase Five)")


def test_a_character_block_names_who_plays_its_variants():
    row = {"profile": "Kang (Earth-616).", "summary": None, "variants": [
        {"label": "He Who Remains", "reality": "Earth-616", "actors": ["Jonathan Majors"]},
        {"label": "Kang", "reality": "Multiverse", "actors": []}]}
    assert character_block(row, []) == ("## Character: Kang (Earth-616).\n"
                                        "Variants' actors: He Who Remains [Earth-616]: Jonathan Majors")


def candidate(kind, key, *names, weight=1):
    return {"kind": kind, "key": key, "names": list(names), "weight": weight}


def keys(question, candidates):
    return [c["key"] for c in entry_points(question, candidates)]


def test_a_name_matches_only_as_a_whole_phrase_with_its_capitals():
    assert name_spans("Who plays Thor?", ["Thor"]) == {(10, 14)}
    assert name_spans("Who is Thoren?", ["Thor"]) == set()
    assert name_spans("Is Vision a robot? Is it a vision?", ["Vision"]) == {(3, 9)}
    assert name_spans("Who leads the Fantastic Four of Earth-828?", ["Earth"]) == set()     # a hyphen joins words


def test_a_one_word_name_at_the_start_is_skipped_as_a_sentence_capital():
    assert name_spans("Who plays Kang?", ["Who", "Kang"]) == {(10, 14)}
    assert name_spans("Thanos snaps.", ["Thanos"]) == set()
    assert name_spans("Thanos snaps.", ["Thanos"], skip_start=False) == {(0, 6)}
    assert name_spans("Iron Man flies.", ["Iron Man"]) == {(0, 8)}


def test_the_longest_overlapping_match_wins_and_shared_names_are_all_kept():
    candidates = [candidate("Title", "Q1", "Avengers: Endgame"), candidate("Team", "T1", "Avengers"),
                  candidate("Character", "C1", "Loki", weight=5), candidate("Character", "C2", "Loki", weight=9)]
    assert keys("Which Avengers: Endgame scenes show Loki?", candidates) == ["Q1", "C2", "C1"]
    assert keys("Which Avengers fought Loki?", candidates) == ["T1", "C2", "C1"]


def test_the_lowercase_the_ties_a_title_with_a_team_of_the_bare_name():
    candidates = [candidate("Title", "Q1", "The Avengers"), candidate("Team", "T1", "Avengers"),
                  candidate("Group", "saga", "The Infinity Saga")]
    assert keys("Who leads the Avengers now?", candidates) == ["Q1", "T1"]
    assert keys("Is The Avengers the first team-up?", candidates) == ["Q1"]
    assert keys("What is the Infinity Saga about?", candidates) == ["saga"]


def test_lucene_text_drops_syntax_and_fuse_ranks_items_found_by_both():
    assert lucene_text('Who is "Natalie Rushman" (AND Nat)?') == "Who is Natalie Rushman and Nat"
    assert fuse([["a", "b"], ["b", "c"]]) == ["b", "a", "c"]


def test_a_title_line_gives_release_setting_place_and_numbers():
    t = {"title": "Captain Marvel", "qid": "Q1", "type": "Film", "year": 2019, "first_release_date": "2019-03-08",
         "start_year": 1995, "end_year": 1995, "universe": "MCU", "reality": "Earth-616", "phases": ["Phase Three"],
         "sagas": ["The Infinity Saga"], "release_order": 21, "chronological_order": 3, "box_office_usd": 1131416446,
         "budget_usd": None, "runtime_minutes": 124, "tmdb_rating": 6.7, "tmdb_votes": 16000}
    assert title_line(t) == ("Captain Marvel [Q1] (Film, released 2019-03-08; set 1995 to 1995; universe MCU; "
                             "reality Earth-616; phases: Phase Three; sagas: The Infinity Saga; release order 21, "
                             "in-universe order 3; box office $1,131,416,446; runtime 124 min; TMDB rating 6.7 (16000 votes))")


def test_a_person_block_groups_roles_by_character():
    row = {"name": "Chris Evans", "born": "1981-06-13", "directed": [], "wrote": [], "other_credits": [],
           "roles": [{"character": "Johnny Storm", "reality": "Earth-121698", "title": "Fantastic Four", "year": 2005,
                      "credited": ["Johnny Storm"]},
                     {"character": "Steve Rogers", "reality": "Earth-616", "title": "Captain America: The First Avenger",
                      "year": 2011, "credited": []},
                     {"character": "Johnny Storm", "reality": "Earth-121698", "title": "Rise of the Silver Surfer",
                      "year": 2007, "credited": []}]}
    assert person_block(row).split("\n") == [
        "## Person: Chris Evans (born 1981-06-13)",
        'Plays Johnny Storm [Earth-121698] in: Fantastic Four (2005) as "Johnny Storm", Rise of the Silver Surfer (2007)',
        "Plays Steve Rogers [Earth-616] in: Captain America: The First Avenger (2011)"]


def test_the_context_is_cut_at_line_ends_and_keeps_room_for_the_search_hits():
    entries = ["## A\n" + "\n".join("a" * 9 for _ in range(20))]
    text = fit(entries, ["## Hit\nh"], max_chars=100, search_chars=20)
    assert len(text) <= 100 and text.endswith("## Hit\nh") and CUT in text
    assert fit(["## A\nshort"], [], max_chars=100) == "## A\nshort"


def test_a_shared_block_lists_what_two_titles_or_teams_have_in_common_or_says_none():
    rows = [{"label": "Nebula", "reality": "Earth-616"}, {"label": "Thor", "reality": "Earth-616"}]
    assert shared_block("Team", "Avengers", "Guardians of the Galaxy", rows) == (
        "## Characters who are members of both: Avengers and Guardians of the Galaxy (2)\n"
        "Nebula [Earth-616], Thor [Earth-616]")
    assert shared_block("Title", "Logan", "Eternals", []) == "## Characters in both casts: Logan and Eternals (0)\nnone"


def test_a_shared_name_is_written_as_the_block_headers_write_it():
    assert shared_name({"kind": "Title", "key": "Q1", "names": ["Fantastic Four", "FF"]}) == "Fantastic Four [Q1]"
    assert shared_name({"kind": "Team", "key": "Avengers@Earth-616", "names": ["Avengers"]}) == "Avengers [Earth-616]"
