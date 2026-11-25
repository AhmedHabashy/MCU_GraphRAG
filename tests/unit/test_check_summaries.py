"""Unit tests for src/graph/check_summaries.py (no files, no database)."""

from src.graph.check_summaries import check, unknown_names

INPUT = {"kind": "character", "id": "S@Multiverse", "name": "Sylvie", "input_hash": "abc", "text": (
    "Sylvie (Multiverse). Played by: Sophia Di Martino (2 titles).\n\nPlot facts (release order):\n"
    '[Q107185252 ep 1] Sylvie ENEMY_OF Time Variance Authority: "Sylvie attacks the TVA."\n'
    '[Q107185252 ep 6] Sylvie KILLS He Who Remains: "Sylvie kills He Who Remains."')}
WORDS = " ".join(["word"] * 70)


def output(**changes):
    base = {"kind": "character", "id": "S@Multiverse", "name": "Sylvie", "input_hash": "abc",
            "summary": f"Sylvie fights the Time Variance Authority and kills He Who Remains. {WORDS}",
            "key_facts": [{"fact": "Sylvie attacks the TVA.", "cite": "[Q107185252 ep 1]"},
                          {"fact": "Sylvie kills He Who Remains.", "cite": "[Q107185252 ep 6]"},
                          {"fact": "Sophia Di Martino plays Sylvie.", "cite": "[Q107185252 ep 1] [Q107185252 ep 6]"}],
            "writer": "claude-sonnet-5.5 subagent"}
    return {**base, **changes}


def test_a_good_output_has_no_problems():
    assert check(INPUT, output()) == ([], [])


def test_the_copied_fields_must_match_the_input():
    problems, _ = check(INPUT, output(input_hash="old", name="Loki"))
    assert any("input_hash" in p for p in problems) and any("name" in p for p in problems)


def test_missing_fields_are_problems():
    bad = output()
    del bad["key_facts"]
    problems, _ = check(INPUT, bad)
    assert any("key_facts" in p for p in problems)


def test_the_summary_must_be_between_60_and_250_words():
    assert any("words" in p for p in check(INPUT, output(summary="Too short."))[0])
    assert any("words" in p for p in check(INPUT, output(summary=" ".join(["word"] * 251)))[0])


def test_key_facts_must_be_three_to_ten_and_cite_citations_of_the_input():
    assert any("key facts" in p for p in check(INPUT, output(key_facts=output()["key_facts"][:2]))[0])
    wrong = output()["key_facts"][:2] + [{"fact": "Sylvie meets Loki.", "cite": "[Q107185252 ep 3]"}]
    assert any("[Q107185252 ep 3]" in p for p in check(INPUT, output(key_facts=wrong))[0])
    uncited = output()["key_facts"][:2] + [{"fact": "Sylvie meets Loki.", "cite": "season one"}]
    assert any("cite" in p for p in check(INPUT, output(key_facts=uncited))[0])


def test_names_the_input_never_mentions_are_warnings_not_problems():
    summary = f"Sylvie kills He Who Remains with help from Mobius. After that she leaves. {WORDS}"
    problems, warnings = check(INPUT, output(summary=summary))
    assert problems == [] and warnings == ["names not in the input: Mobius"]


def test_unknown_names_skip_a_capitalized_word_that_only_starts_a_sentence():
    assert unknown_names("After the fight, Sylvie rests. Then Kang appears.", INPUT["text"]) == ["Kang"]
