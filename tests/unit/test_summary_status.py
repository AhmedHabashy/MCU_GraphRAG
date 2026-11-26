"""Unit tests for src/graph/summary_status.py (temporary files only; no database)."""

import json
import os

from src.graph.summary_status import MAX_REWRITES, fresh_check, state

INP = {"kind": "title", "id": "Q1", "name": "Iron Man", "input_hash": "h1", "text": "..."}
OUT = {"input_hash": "h1", "rewrites": 0}
PASS, FAIL = {"verdict": "pass"}, {"verdict": "fail"}


def test_a_summary_without_an_output_or_for_another_input_is_to_write():
    assert state(INP, None, [], None, None) == ("write", None)
    assert state(INP, {"input_hash": "old", "rewrites": 2}, [], PASS, PASS) == ("write", None)


def test_a_summary_with_problems_is_to_fix_before_any_check():
    assert state(INP, OUT, ["summary has 20 words"], None, None) == ("fix", None)


def test_checks_come_one_after_the_other():
    assert state(INP, OUT, [], None, None) == ("check1", None)
    assert state(INP, OUT, [], PASS, None) == ("check2", None)
    assert state(INP, OUT, [], None, PASS) == ("check1", None)       # check 2 never counts without check 1
    assert state(INP, OUT, [], PASS, PASS) == ("kept", None)


def test_a_failed_check_means_a_rewrite_until_the_rewrites_run_out():
    assert state(INP, OUT, [], FAIL, None) == ("rewrite", "check1")
    assert state(INP, OUT, [], PASS, FAIL) == ("rewrite", "check2")
    assert state(INP, dict(OUT, rewrites=MAX_REWRITES), [], PASS, FAIL) == ("flagged", "check2")
    assert state(INP, {"input_hash": "h1"}, [], FAIL, None) == ("rewrite", "check1")   # no field: 0 rewrites


def test_a_review_sends_even_a_kept_summary_back_for_a_rewrite():
    """Wave 3: two checks passed "is consoled by her angrily", where the input has Fisk angry."""
    assert state(INP, OUT, [], PASS, PASS, review=FAIL) == ("rewrite", "review")
    assert state(INP, dict(OUT, rewrites=MAX_REWRITES), [], PASS, PASS, review=FAIL) == ("flagged", "review")
    assert state(INP, OUT, [], PASS, PASS, review=None) == ("kept", None)
    assert state(INP, None, [], None, None, review=FAIL) == ("write", None)    # a new input comes first


def test_a_check_counts_only_when_newer_than_the_summary_and_well_formed(tmp_path):
    summary, check = tmp_path / "s.json", tmp_path / "s.check1.json"
    summary.write_text("{}")
    assert fresh_check(check, summary) is None                          # missing
    check.write_text(json.dumps({"verdict": "pass"}))
    os.utime(summary, (2_000_000, 2_000_000))
    os.utime(check, (1_000_000, 1_000_000))
    assert fresh_check(check, summary) is None                          # older: checked an earlier version
    os.utime(check, (3_000_000, 3_000_000))
    assert fresh_check(check, summary) == {"verdict": "pass"}
    check.write_text(json.dumps({"verdict": "maybe"}))
    os.utime(check, (3_000_000, 3_000_000))
    assert fresh_check(check, summary) is None                          # no valid verdict: check again


def test_a_check_that_lumps_the_key_facts_together_does_not_count(tmp_path):
    """Wave 3: a checker gave each summary's key facts one statement ("Key facts (5) match")."""
    summary, check = tmp_path / "s.json", tmp_path / "s.check2.json"
    summary.write_text(json.dumps({"key_facts": [{"fact": "a"}, {"fact": "b"}, {"fact": "c"}]}))
    check.write_text(json.dumps({"verdict": "pass", "statements": [{"text": "s1"}, {"text": "Key facts (3) match"}]}))
    os.utime(summary, (1_000_000, 1_000_000))
    os.utime(check, (2_000_000, 2_000_000))
    assert fresh_check(check, summary) is None
    check.write_text(json.dumps({"verdict": "pass", "statements": [{"text": f"s{i}"} for i in range(4)]}))
    os.utime(check, (2_000_000, 2_000_000))
    assert fresh_check(check, summary)["verdict"] == "pass"
    review = tmp_path / "review.json"         # a review names only what is wrong
    review.write_text(json.dumps({"verdict": "fail", "statements": [{"text": "x", "supported": False}]}))
    os.utime(review, (2_000_000, 2_000_000))
    assert fresh_check(review, summary, whole=False)["verdict"] == "fail"
