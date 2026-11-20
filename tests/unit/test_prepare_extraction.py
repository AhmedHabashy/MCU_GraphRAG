"""Unit tests for src/graph/prepare_extraction.py."""

import os

from src.graph.prepare_extraction import batches, chunk_inputs, pending, text_chunks, title_cast


def episode(n, summary, season=1):
    return {"number_overall": n, "season": season, "number_in_season": n, "title": f"Ep {n}",
            "summary_text": summary}


def test_a_film_is_one_chunk():
    assert text_chunks({"text": "Wade meets Logan.", "episodes": []}) == ["Wade meets Logan."]


def test_series_chunks_keep_whole_episodes_within_the_limit():
    plot = {"text": "", "episodes": [episode(1, "a" * 40), episode(2, "b" * 40), episode(3, "c" * 40)]}
    chunks = text_chunks(plot, max_chars=170)  # each episode is ~77 chars with its header
    assert len(chunks) == 2 and chunks[0].count("Episode ") == 2 and chunks[1].startswith("Episode 3")


def test_episodes_are_numbered_across_the_series():
    assert text_chunks({"episodes": [episode(23, "x", season=2)]})[0].startswith("Episode 23 (season 2, episode 23)")


def test_chunk_ids_are_the_title_or_its_parts():
    film = chunk_inputs({"title": "F", "title_qid": "Q1", "text": "t"}, [], [])
    series = chunk_inputs({"title": "S", "title_qid": "Q2", "episodes": [episode(1, "a" * 30000), episode(2, "b")]}, [], [])
    assert list(film) == ["Q1"] and list(series) == ["Q2_part1", "Q2_part2"]


def test_cast_lists_each_character_once_without_its_label_as_an_alias():
    perfs = [{"title_qid": "Q1", "character_id": "C@E", "actor_name": "A"},
             {"title_qid": "Q1", "character_id": "C@E", "actor_name": "A"},
             {"title_qid": "Q9", "character_id": "D@E", "actor_name": "B"}]
    cast = title_cast("Q1", perfs, {"C@E": {"label": "Wade", "reality": "E"}}, {"C@E": {"Wade", "Deadpool"}})
    assert cast == [{"id": "C@E", "label": "Wade", "reality": "E", "actor": "A", "aliases": ["Deadpool"]}]


def test_pending_chunks_have_no_output_or_an_older_one(tmp_path):
    inputs, outputs = tmp_path / "in", tmp_path / "out"
    inputs.mkdir(), outputs.mkdir()
    for cid in ("done", "new", "changed"):
        (inputs / f"{cid}.json").write_text("{}")
    (outputs / "done.json").write_text("{}")
    (outputs / "changed.json").write_text("{}")
    os.utime(outputs / "changed.json", (1, 1))  # written before its input
    assert pending(["done", "new", "changed"], inputs, outputs) == ["new", "changed"]


def test_batches_group_chunks_up_to_the_text_budget():
    assert batches([("a", 30), ("b", 20), ("c", 50), ("d", 5)], batch_chars=50) == [["a", "b"], ["c"], ["d"]]
