"""Unit tests for src/retrieval/passages.py (no network, no database)."""

from src.retrieval.passages import embed_new, group_paragraphs, plot_passages

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


class FakeEmbedder:
    embedding_model = "embed/model"

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return [[float(len(t))] for t in texts]


def test_only_passages_without_a_vector_from_this_model_are_embedded_and_old_ones_dropped():
    passages = plot_passages(FILM, max_chars=40)
    cache = {"model": "embed/model", "vectors": {passages[0]["id"]: [9.0], "gone": [1.0]}}
    embedder = FakeEmbedder()
    cache, embedded = embed_new(passages, cache, embedder)
    assert embedded == 1 and len(embedder.calls) == 1 and len(embedder.calls[0]) == 1
    assert embedder.calls[0][0].startswith("Iron Man\n")          # the heading is embedded with the text
    assert set(cache["vectors"]) == {p["id"] for p in passages} and cache["vectors"][passages[0]["id"]] == [9.0]


def test_a_new_embedding_model_embeds_everything_again():
    passages = plot_passages(FILM, max_chars=40)
    cache = {"model": "old/model", "vectors": {p["id"]: [9.0] for p in passages}}
    cache, embedded = embed_new(passages, cache, FakeEmbedder())
    assert embedded == 2 and cache["model"] == "embed/model"


def test_nothing_new_means_no_request():
    passages = plot_passages(FILM, max_chars=40)
    embedder = FakeEmbedder()
    _, embedded = embed_new(passages, {"model": "embed/model", "vectors": {p["id"]: [1.0] for p in passages}}, embedder)
    assert embedded == 0 and embedder.calls == []
