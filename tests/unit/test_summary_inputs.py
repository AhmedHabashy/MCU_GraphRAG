"""Unit tests for src/graph/summary_inputs.py (no database, no files)."""

from src.graph.summary_inputs import (
    batches, citations, fact_line, facts_text, group_input, group_inputs, is_main_character, is_pending, make_input,
    reality_sources, summary_block, title_inputs, title_text,
)

FILM = {"title": "Iron Man", "title_qid": "Q1", "type": "Film", "text": "Tony is captured.\n\nHe escapes.",
        "episodes": []}
SERIES = {"title": "Loki, season 1", "title_qid": "Q2", "type": "Series season", "text": "", "episodes": [
    {"number_overall": 1, "season": 1, "number_in_season": 1, "title": "Glorious Purpose",
     "summary_text": "Loki is arrested."},
    {"number_overall": 2, "season": 1, "number_in_season": 2, "title": "Untitled", "summary_text": ""}]}


def test_the_hash_is_stable_and_changes_with_the_text():
    a, b = make_input("title", "Q1", "Iron Man", 1, ["Q1"], "text"), make_input("title", "Q1", "Iron Man", 1, ["Q1"], "text")
    assert a["input_hash"] == b["input_hash"]
    assert make_input("title", "Q1", "Iron Man", 1, ["Q1"], "text!")["input_hash"] != a["input_hash"]


def test_a_summary_is_pending_without_an_output_or_with_an_outdated_one():
    inp = make_input("title", "Q1", "Iron Man", 1, ["Q1"], "text")
    assert is_pending(inp, None)
    assert is_pending(inp, {"input_hash": "old"})
    assert not is_pending(inp, {"input_hash": inp["input_hash"]})


def test_a_film_plot_is_cited_once_and_a_series_cites_each_episode_with_a_summary():
    assert title_text(FILM) == "[Q1]\nTony is captured.\n\nHe escapes."
    assert title_text(SERIES) == "[Q2 ep 1] Episode 1 (season 1, episode 1): Glorious Purpose\nLoki is arrested."
    assert citations(title_text(SERIES)) == {("Q2", 1)} and citations(title_text(FILM)) == {("Q1", None)}


def test_a_fact_line_cites_and_names_its_title_and_keeps_evidence_and_note():
    """The title's name is given, so the writer need not guess which film a citation is (pilot)."""
    fact = {"title_qid": "Q2", "title": "Loki, season 1", "episode": 6, "subject": "Sylvie", "relation": "KILLS",
            "object": "He Who Remains", "evidence": "Sylvie kills He Who Remains.", "note": ""}
    assert fact_line(fact) == '[Q2 ep 6] Loki, season 1: Sylvie KILLS He Who Remains: "Sylvie kills He Who Remains."'
    assert fact_line(dict(fact, episode=None, note="undone later")) == \
        '[Q2] Loki, season 1: Sylvie KILLS He Who Remains: "Sylvie kills He Who Remains." (note: undone later)'


def test_facts_of_one_title_are_in_story_order_by_where_their_evidence_appears_in_the_plot():
    """Wave 8: a film's facts were sorted by relation, so Thor 'defeats Surtur' came after Sakaar."""
    plot = {"title": "Thor: Ragnarok", "title_qid": "Q9", "text": "Thor is imprisoned by Surtur. Thor defeats Surtur. "
            "Thor crash-lands on Sakaar.", "episodes": []}
    def f(relation, evidence):
        return {"title_qid": "Q9", "title": "Thor: Ragnarok", "order": 1, "episode": None, "subject": "Thor",
                "relation": relation, "object": "x", "evidence": evidence, "note": ""}
    facts = [f("TRAVELS_TO", "Thor crash-lands on Sakaar"), f("ENEMY_OF", "Thor is imprisoned by Surtur"),
             f("KILLS", "Thor defeats Surtur"), f("ALLY_OF", "not in the plot")]
    lines = facts_text(facts, {"Q9": plot}).splitlines()
    assert [l.split('"')[1] for l in lines] == ["Thor is imprisoned by Surtur", "Thor defeats Surtur",
                                                "Thor crash-lands on Sakaar", "not in the plot"]   # unfound go last


def test_main_characters_have_five_plot_facts_or_three_titles_and_at_least_one_fact():
    """A character with no plot fact gets no written summary: it would only restate the profile,
    and its key facts would have nothing to cite (wave 1: Flash Thompson, Stan Lee's cameo)."""
    assert is_main_character(facts=5, titles=1) and is_main_character(facts=1, titles=3)
    assert not is_main_character(facts=4, titles=2) and not is_main_character(facts=0, titles=19)


OUTPUTS = {("title", "Q1"): {"name": "Iron Man", "summary": "Tony becomes Iron Man.", "input_hash": "h1",
                             "key_facts": [{"fact": "Tony builds a suit.", "cite": "[Q1]"}]},
           ("title", "Q3"): {"name": "Iron Man 2", "summary": "Tony faces Vanko.", "input_hash": "h3",
                             "key_facts": []}}


def test_a_summary_block_carries_the_lower_summary_and_its_cited_key_facts():
    assert summary_block("title", "Q1", OUTPUTS[("title", "Q1")]) == \
        "## Iron Man [Q1]\nTony becomes Iron Man.\nKey facts:\n- Tony builds a suit. [Q1]"


def test_a_group_input_is_built_only_when_every_member_summary_exists():
    inp = group_input("series", "Q1", "Iron Man series", 2, "title", ["Q1", "Q3"], OUTPUTS)
    assert inp["sources"] == [["title", "Q1"], ["title", "Q3"]] and "Tony faces Vanko." in inp["text"]
    assert group_input("series", "Q1", "Iron Man series", 2, "title", ["Q1", "Q9"], OUTPUTS) is None


def test_a_rewritten_member_summary_changes_the_group_hash():
    before = group_input("phase", "phase-one", "Phase One", 2, "title", ["Q1", "Q3"], OUTPUTS)
    changed = {**OUTPUTS, ("title", "Q3"): dict(OUTPUTS[("title", "Q3")], summary="Tony fights Vanko.")}
    after = group_input("phase", "phase-one", "Phase One", 2, "title", ["Q1", "Q3"], changed)
    assert before["input_hash"] != after["input_hash"]


def test_a_reality_uses_a_universe_summary_only_for_universes_wholly_in_it():
    title_reality = {"T1": "Earth-10005", "T2": "Earth-10005", "T3": "Earth-10005", "T4": "Earth-616"}
    title_universe = {"T1": "Fox X-Men", "T2": "Fox X-Men", "T3": "MCU", "T4": "MCU"}
    assert reality_sources("Earth-10005", title_reality, title_universe) == [
        ("universe", "Fox X-Men"), ("title", "T3")]


LONG = {"title": "Saga Show", "title_qid": "Q5", "type": "Series", "text": "", "episodes": [
    {"number_overall": n, "season": s, "number_in_season": n, "title": f"E{n}", "summary_text": "x" * 40}
    for n, s in ((1, 1), (2, 1), (3, 2))]}
TITLES = [{"qid": "Q5", "title": "Saga Show", "type": "Series", "year": 2020, "universe": "TV", "reality": "Earth-616",
           "phases": [], "sagas": [], "release_order": 1}]


def test_a_title_too_long_for_one_input_is_written_from_its_season_digests():
    items = {(k, i): inp for k, i, inp in title_inputs(TITLES, {"Q5": LONG}, outputs={}, max_chars=100)}
    assert set(items) == {("season", "Q5-s1"), ("season", "Q5-s2"), ("title", "Q5")}
    assert items[("title", "Q5")] is None                                  # waits for its seasons
    assert items[("season", "Q5-s1")]["name"] == "Saga Show, season 1"
    assert citations(items[("season", "Q5-s2")]["text"]) == {("Q5", 3)}
    seasons = {("season", f"Q5-s{s}"): {"name": f"Saga Show, season {s}", "summary": f"season {s}", "key_facts": []}
               for s in (1, 2)}
    title = dict(title_inputs(TITLES, {"Q5": LONG}, outputs=seasons, max_chars=100)[-1][2])
    assert title["sources"] == [["season", "Q5-s1"], ["season", "Q5-s2"]] and "season 2" in title["text"]
    short = title_inputs(TITLES, {"Q5": LONG}, outputs={}, max_chars=10_000)
    assert [(k, i) for k, i, _ in short] == [("title", "Q5")]


def group_titles():
    def t(qid, universe, reality, phases):
        return {"qid": qid, "title": f"T{qid}", "universe": universe, "reality": reality, "phases": phases,
                "sagas": [], "release_order": int(qid[1:])}
    return [t("Q1", "MCU", "Earth-616", ["Phase One"]), t("Q2", "MCU", "Earth-616", ["Phase Two"]),
            t("Q3", "MCU", "Earth-10005", ["Phase Two"]), t("Q4", "MCU animation", "Earth-616", ["Phase Two"]),
            t("Q5", "Netflix", "Earth-616", [])]


def stub(kind, id_, size=10):
    return (kind, id_), {"name": id_, "summary": "s" * size, "key_facts": []}


def test_a_universe_too_big_from_digests_is_built_from_its_phases_and_names_their_other_titles():
    outputs = dict([stub("title", q, 60) for q in ("Q1", "Q2", "Q3", "Q4", "Q5")]
                   + [stub("phase", p) for p in ("Phase One", "Phase Two")])
    items = {(k, i): inp for k, i, inp in group_inputs(group_titles(), [], outputs, max_chars=150)}
    mcu = items[("universe", "MCU")]
    assert mcu["sources"] == [["phase", "Phase One"], ["phase", "Phase Two"]]
    assert "TQ4" in mcu["text"].split("\n\n")[0]          # the note: Phase Two also covers an MCU animation title
    assert items[("universe", "Netflix")]["sources"] == [["title", "Q5"]]           # small enough from its digest


def test_a_reality_too_big_from_digests_takes_its_universes_whole_and_names_their_other_titles():
    outputs = dict([stub("title", q, 60) for q in ("Q1", "Q2", "Q3", "Q4", "Q5")]
                   + [stub("universe", u) for u in ("MCU", "MCU animation", "Netflix")]
                   + [stub("phase", p) for p in ("Phase One", "Phase Two")])
    items = {(k, i): inp for k, i, inp in group_inputs(group_titles(), [], outputs, max_chars=200)}
    earth_616 = items[("reality", "Earth-616")]
    assert earth_616["sources"] == [["universe", "MCU"], ["universe", "MCU animation"], ["universe", "Netflix"]]
    note = earth_616["text"].split("\n\n")[0]
    assert "TQ3" in note and "Earth-10005" in note


def test_batches_group_inputs_up_to_a_size_and_never_split_one():
    inputs = [make_input("title", f"Q{i}", "t", 1, [], "x" * n) for i, n in enumerate((30, 30, 50, 10))]
    assert [[b["id"] for b in batch] for batch in batches(inputs, max_chars=60)] == [["Q0", "Q1"], ["Q2", "Q3"]]


def test_a_batch_holds_at_most_a_set_number_of_summaries():
    """Wave 1: an agent given 43 small summaries took 11 minutes and wrote other batches too."""
    inputs = [make_input("character", f"C{i}", "c", 1, [], "x") for i in range(45)]
    assert [len(batch) for batch in batches(inputs, max_chars=10_000, max_items=20)] == [20, 20, 5]
