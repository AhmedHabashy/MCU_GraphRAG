"""Unit tests for src/retrieval/passages.py (no network, no database)."""

from src.retrieval.passages import embedded_text, group_paragraphs, plot_passages

FILM = {"title": "Iron Man", "title_qid": "Q1", "text": "Tony is captured.\n\nHe builds a suit.\n\nHe escapes.",
        "episodes": []}


def episode(n, title, summary, part=1, parts=1):
    return {"number_overall": n, "season": 1, "number_in_season": n, "title": title, "summary_text": summary,
            "part": part, "num_parts": parts}


SERIES = {"title": "X-Men '97", "title_qid": "Q2", "text": "", "episodes": [
    episode(1, "To Me, My X-Men", "Cyclops leads."),
    episode(2, "Tolerance Is Extinction", "Genosha falls.", 1, 2),
    episode(3, "Tolerance Is Extinction", "Genosha falls.", 2, 2),
    episode(4, "Untitled", "")]}


def test_paragraphs_are_grouped_whole_up_to_the_size_limit():
    assert group_paragraphs("aaaa\n\nbbbb\ncccc\n\n", max_chars=10) == ["aaaa\n\nbbbb", "cccc"]
    assert group_paragraphs("a" * 30, max_chars=10) == ["a" * 30]     # a long paragraph is kept whole


def test_a_film_plot_gives_passages_headed_by_its_title():
    passages = plot_passages(FILM, max_chars=40)
    assert [p["text"] for p in passages] == ["Tony is captured.\n\nHe builds a suit.", "He escapes."]
    assert all(p["title_qid"] == "Q1" and p["episodes"] == [] and p["heading"] == "Iron Man" for p in passages)


def test_a_series_gives_passages_per_episode_and_one_for_episodes_sharing_a_summary():
    passages = plot_passages(SERIES)
    assert [(p["episodes"], p["text"]) for p in passages] == [([1], "Cyclops leads."), ([2, 3], "Genosha falls.")]
    assert passages[1]["heading"] == "X-Men '97, episodes 2-3 (season 1): Tolerance Is Extinction"
    assert passages[0]["heading"] == "X-Men '97, episode 1 (season 1): To Me, My X-Men"


def test_a_passage_id_is_stable_and_changes_with_its_text():
    first, again = plot_passages(FILM, max_chars=40), plot_passages(FILM, max_chars=40)
    assert [p["id"] for p in first] == [p["id"] for p in again]
    edited = plot_passages(dict(FILM, text=FILM["text"].replace("escapes", "flies away")), max_chars=40)
    assert edited[0]["id"] == first[0]["id"] and edited[1]["id"] != first[1]["id"]


def test_the_heading_is_embedded_with_the_text():
    assert embedded_text(plot_passages(FILM, max_chars=40)[1]) == "Iron Man\nHe escapes."
