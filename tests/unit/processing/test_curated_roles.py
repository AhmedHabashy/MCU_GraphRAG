"""Unit tests for src/processing/curated_roles.py."""

from src.processing.curated_roles import apply_curated_roles, unmatched_rows

TITLE_QIDS = {"Spider-Man: No Way Home": "Q68934496", "Deadpool & Wolverine": "Q102180106",
              "Spider-Man: Homecoming": "Q23010088", "Avengers: Endgame": "Q23781155"}
TITLE_REALITIES = {"Q68934496": "Earth-616", "Q102180106": "Earth-10005",
                   "Q23010088": "Earth-616", "Q23781155": "Earth-616"}


def curated(title, actor, character="", identity="", reality="", variant_of=""):
    return {"title": title, "actor": actor, "character": character, "identity": identity,
            "reality": reality, "variant of": variant_of, "needs_review": False}


def perf(title_qid, actor, base, cid, source="tmdb"):
    return {"title_qid": title_qid, "actor_name": actor, "base_qid": base, "character_id": cid,
            "source": source}


def apply(performances, rows):
    return apply_curated_roles(performances, rows, TITLE_QIDS, TITLE_REALITIES)


def test_curated_reality_replaces_the_computed_one():
    [p] = apply([perf("Q68934496", "Alfred Molina", "Q578094", "Q578094@Earth-616")],
                [curated("Spider-Man: No Way Home", "Alfred Molina", "Doctor Octopus", reality="Earth-96283")])
    assert p["character_id"] == "Q578094@Earth-96283" and p["curated"] is True
    assert p["curated_label"] == "Doctor Octopus"


def test_curated_identity_and_variant_of():
    [p] = apply([perf("Q102180106", "Hugh Jackman", "mcuwiki:Wolverine", "mcuwiki:Wolverine@Earth-10005")],
                [curated("Deadpool & Wolverine", "Hugh Jackman", "Wolverine", "mcuwiki:Wolverine",
                         "Unknown", "Q97275436")])
    assert (p["base_qid"], p["character_id"], p["curated_variant_of"]) == \
        ("mcuwiki:Wolverine", "mcuwiki:Wolverine@Unknown", "Q97275436")


def test_a_curated_identity_keeps_the_character_the_data_linked():
    [p] = apply([perf("Q23010088", "Kerry Condon", "Q107088537", "Q107088537@Earth-616")],
                [curated("*", "Kerry Condon", "F.R.I.D.A.Y.", "Q28173125")])
    assert (p["base_qid"], p["data_base_qid"]) == ("Q28173125", "Q107088537")


def test_star_title_applies_to_every_title():
    rows = apply([perf("Q23010088", "Kerry Condon", "Q107088537", "Q107088537@Earth-616"),
                  perf("Q23781155", "Kerry Condon", "Q107088537", "Q107088537@Earth-616")],
                 [curated("*", "Kerry Condon", "F.R.I.D.A.Y.", "mcuwiki:F.R.I.D.A.Y.")])
    assert {p["character_id"] for p in rows} == {"mcuwiki:F.R.I.D.A.Y.@Earth-616"}


def test_curated_identity_links_an_unlinked_credit_in_the_title_reality():
    [p] = apply([perf("Q23010088", "Kerry Condon", "", "")],
                [curated("*", "Kerry Condon", "F.R.I.D.A.Y.", "mcuwiki:F.R.I.D.A.Y.")])
    assert p["character_id"] == "mcuwiki:F.R.I.D.A.Y.@Earth-616"


def test_other_roles_are_untouched():
    before = perf("Q68934496", "Tom Holland", "Q1", "Q1@Earth-616")
    [p] = apply([dict(before)], [curated("Spider-Man: No Way Home", "Alfred Molina", reality="Earth-96283")])
    assert p == {**before, "curated": False, "curated_label": "", "curated_variant_of": "",
                 "data_base_qid": "Q1"}


def test_actor_names_match_ignoring_case_and_accents():
    [p] = apply([perf("Q68934496", "Alfred MOLINA", "Q578094", "Q578094@Earth-616")],
                [curated("Spider-Man: No Way Home", "Alfred Molina", reality="Earth-96283")])
    assert p["character_id"] == "Q578094@Earth-96283"


def test_unmatched_rows_are_reported():
    rows = [curated("Spider-Man: No Way Home", "Alfred Molina", reality="Earth-96283"),
            curated("Spider-Man: No Way Home", "Alfred Molino", reality="Earth-96283")]   # typo
    performances = [perf("Q68934496", "Alfred Molina", "Q578094", "Q578094@Earth-616")]
    assert [r["actor"] for r in unmatched_rows(performances, rows, TITLE_QIDS)] == ["Alfred Molino"]
