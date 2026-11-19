"""Unit tests for src/source_data_collection/collect_plots.py (fake client, no network)."""

from src.source_data_collection.collect_plots import plot_record, wikidata_episodes


def section(page, heading, wikitext, revid=1):
    return {"page": page, "revid": revid, "heading": heading, "index": "1", "wikitext": wikitext}


class FakeClient:
    def __init__(self, sections, entities=None):
        self.sections = sections        # (page, first prefix) -> section
        self.entities = entities or {}
        self.requests = []

    def top_level_section(self, page, prefix):
        prefixes = (prefix,) if isinstance(prefix, str) else prefix
        self.requests.append((page, prefixes))
        return next((self.sections[(page, p)] for p in prefixes if (page, p) in self.sections), None)

    def get_entities(self, ids, props=None):
        return {q: self.entities[q] for q in ids if q in self.entities}


def episode(number, title, summary, season_number=None):
    second = f"|EpisodeNumber2 = {season_number}\n" if season_number else ""
    return (f"{{{{Episode list\n|EpisodeNumber = {number}\n{second}|Title = {title}\n"
            f"|OriginalAirDate = {{{{Start date|2021|6|{number}}}}}\n"
            f"|ShortSummary = {summary}\n}}}}")


IRON_MAN = {"title": "Iron Man", "type": "Film", "wikidata_qid": "Q192724",
            "enwiki_title": "Iron Man (2008 film)", "season_number": ""}


def test_film_record_uses_the_plot_section():
    client = FakeClient({("Iron Man (2008 film)", "Plot"): section(
        "Iron Man (2008 film)", "Plot", "== Plot ==\n[[Tony Stark]] builds a suit.", revid=42)})

    record = plot_record(IRON_MAN, client, retrieved_at="t")

    assert record["kind"] == "plot"
    assert record["text"] == "Tony Stark builds a suit."
    assert record["episodes"] == []
    assert record["sections"][0]["revid"] == 42
    assert record["sections"][0]["url"] == "https://en.wikipedia.org/wiki/Iron_Man_(2008_film)"
    assert record["license"] == "CC BY-SA 4.0"
    assert client.requests == [("Iron Man (2008 film)", ("Plot", "Premise"))]


def test_tv_special_uses_the_plot_section_like_a_film():
    special = {**IRON_MAN, "title": "Werewolf by Night", "type": "Special",
               "enwiki_title": "Werewolf by Night (film)"}
    client = FakeClient({("Werewolf by Night (film)", "Plot"): section(
        "Werewolf by Night (film)", "Plot", "== Plot ==\nHunters gather.")})
    assert plot_record(special, client, retrieved_at="t")["kind"] == "plot"


def test_unreleased_film_falls_back_to_premise():
    doomsday = {**IRON_MAN, "title": "Avengers: Doomsday", "enwiki_title": "Avengers: Doomsday"}
    client = FakeClient({("Avengers: Doomsday", "Premise"): section(
        "Avengers: Doomsday", "Premise", "== Premise ==\nThe Avengers face Doom.")})

    record = plot_record(doomsday, client, retrieved_at="t")

    assert record["kind"] == "premise" and record["text"] == "The Avengers face Doom."


def test_season_record_reads_episode_summaries():
    loki = {"title": "Loki, season 1", "type": "Series season", "wikidata_qid": "Q107185252",
            "enwiki_title": "Loki season 1", "season_number": "1"}
    client = FakeClient({("Loki season 1", "Episodes"): section(
        "Loki season 1", "Episodes", "== Episodes ==\n" + episode(1, "Glorious Purpose",
                                                                 "Loki is arrested.", 1))})

    record = plot_record(loki, client, retrieved_at="t")

    assert record["kind"] == "episodes" and record["text"] == ""
    assert [(e["season"], e["number_in_season"], e["title"], e["summary_text"], e["source_page"])
            for e in record["episodes"]] == [(1, 1, "Glorious Purpose", "Loki is arrested.",
                                              "Loki season 1")]


def test_series_record_follows_transcluded_season_pages():
    what_if = {"title": "What If...?", "type": "Animated series", "wikidata_qid": "Q65980671",
               "enwiki_title": "What If...? (TV series)", "season_number": ""}
    client = FakeClient({
        ("What If...? (TV series)", "Episodes"): section(
            "What If...? (TV series)", "Episodes",
            "== Episodes ==\n=== Season 1 ===\n{{:What If...? season 1}}\n"
            "=== Season 2 ===\n{{:What If...? season 2}}"),
        ("What If...? season 1", "Episodes"): section(
            "What If...? season 1", "Episodes", episode(1, "Captain Carter", "Peggy...", 1)),
        ("What If...? season 2", "Episodes"): section(
            "What If...? season 2", "Episodes", episode(10, "Nebula", "Nebula...", 1)),
    })

    record = plot_record(what_if, client, retrieved_at="t")

    assert [(e["season"], e["number_in_season"], e["title"]) for e in record["episodes"]] == [
        (1, 1, "Captain Carter"), (2, 1, "Nebula")]
    assert [s["page"] for s in record["sections"]] == [
        "What If...? (TV series)", "What If...? season 1", "What If...? season 2"]


def test_series_limited_to_seasons_only_follows_those_season_pages():
    what_if = {"title": "What If...?", "type": "Animated series", "wikidata_qid": "Q65980671",
               "enwiki_title": "What If...? (TV series)", "season_number": "", "seasons": "1"}
    client = FakeClient({
        ("What If...? (TV series)", "Episodes"): section(
            "What If...? (TV series)", "Episodes",
            "{{:What If...? season 1}}\n{{:What If...? season 2}}"),
        ("What If...? season 1", "Episodes"): section(
            "What If...? season 1", "Episodes", episode(1, "Captain Carter", "Peggy...", 1)),
        ("What If...? season 2", "Episodes"): section(
            "What If...? season 2", "Episodes", episode(10, "Nebula", "Nebula...", 1)),
    })

    record = plot_record(what_if, client, retrieved_at="t")

    assert [e["season"] for e in record["episodes"]] == [1]
    assert ("What If...? season 2", ("Episodes",)) not in client.requests


def test_series_record_follows_an_episode_list_page_to_its_season_pages():
    """Agents of S.H.I.E.L.D. transcludes 'List of ... episodes', which transcludes each season."""
    shield = {"title": "Agents of S.H.I.E.L.D.", "type": "Series", "wikidata_qid": "Q537911",
              "enwiki_title": "Agents of S.H.I.E.L.D.", "season_number": "", "seasons": "1|2"}
    client = FakeClient({
        ("Agents of S.H.I.E.L.D.", "Episodes"): section(
            "Agents of S.H.I.E.L.D.", "Episodes", "{{:List of Agents of S.H.I.E.L.D. episodes}}"),
        ("List of Agents of S.H.I.E.L.D. episodes", "Episodes"): section(
            "List of Agents of S.H.I.E.L.D. episodes", "Episodes",
            "=== Season 1 ===\n{{:Agents of S.H.I.E.L.D. season 1}}\n"
            "=== Season 3 ===\n{{:Agents of S.H.I.E.L.D. season 3}}"),
        ("Agents of S.H.I.E.L.D. season 1", "Episodes"): section(
            "Agents of S.H.I.E.L.D. season 1", "Episodes", episode(1, "Pilot", "Coulson...", 1)),
        ("Agents of S.H.I.E.L.D. season 3", "Episodes"): section(
            "Agents of S.H.I.E.L.D. season 3", "Episodes", episode(45, "Laws of Nature", "Daisy...", 1)),
    })

    record = plot_record(shield, client, retrieved_at="t")

    assert [(e["season"], e["title"]) for e in record["episodes"]] == [(1, "Pilot")]
    assert [s["page"] for s in record["sections"]] == [
        "Agents of S.H.I.E.L.D.", "List of Agents of S.H.I.E.L.D. episodes", "Agents of S.H.I.E.L.D. season 1"]
    assert ("Agents of S.H.I.E.L.D. season 3", ("Episodes",)) not in client.requests


def test_wikidata_episodes_of_a_series_limited_to_seasons():
    def season(qid, number, episodes):
        return {"id": qid, "claims": {
            "P31": [item("Q3464665")],
            "P179": [{**item("QSERIES"), "qualifiers": {"P1545": [
                {"datavalue": {"type": "string", "value": str(number)}}]}}],
            "P527": [item(e) for e in episodes]}}

    series = {"claims": {"P527": [item("S1"), item("S3")]}}
    client = FakeClient({}, {"S1": season("S1", 1, ["E1"]), "S3": season("S3", 3, ["E3"]),
                             "E1": {"id": "E1", "claims": {}}, "E3": {"id": "E3", "claims": {}}})
    assert [e["id"] for e in wikidata_episodes(series, client, seasons={1, 2})] == ["E1"]


def test_inline_seasons_are_read_from_season_subheadings():
    """I Am Groot lists both seasons in one Episodes section, under 'Season N' subheadings."""
    groot = {"title": "I Am Groot", "type": "Animated shorts", "wikidata_qid": "Q108170999",
             "enwiki_title": "I Am Groot", "season_number": "", "seasons": "1|2"}
    wikitext = ("== Episodes ==\n=== Season 1 (2022) ===\n" + episode(1, "Groot's First Steps", "Groot grows.", 1)
                + "\n=== Season 2 (2023) ===\n" + episode(6, "Groot's Snow Day", "Groot plays.", 1))
    client = FakeClient({("I Am Groot", "Episodes"): section("I Am Groot", "Episodes", wikitext)})

    record = plot_record(groot, client, retrieved_at="2026-11-18T00:00:00Z")

    assert [(e["season"], e["number_in_season"]) for e in record["episodes"]] == [(1, 1), (2, 1)]


def test_episodes_are_marked_aired_only_with_a_past_air_date():
    show = {"title": "Marvel Zombies", "type": "Animated series", "wikidata_qid": "Q111382701",
            "enwiki_title": "Marvel Zombies (TV series)", "season_number": "", "seasons": ""}
    announced = "{{Episode list\n|EpisodeNumber = 5\n|OriginalAirDate = {{Start date|2027|10|}}\n}}"
    client = FakeClient({("Marvel Zombies (TV series)", "Episodes"): section(
        "Marvel Zombies (TV series)", "Episodes", episode(1, "Episode 1", "Zombies.") + announced)})

    record = plot_record(show, client, retrieved_at="2026-11-18T00:00:00Z")

    assert [e["aired"] for e in record["episodes"]] == [True, False]


def test_inline_series_episodes_are_season_one():
    tfatws = {"title": "The Falcon and the Winter Soldier", "type": "Series",
              "wikidata_qid": "Q65979734", "enwiki_title": "The Falcon and the Winter Soldier",
              "season_number": ""}
    client = FakeClient({("The Falcon and the Winter Soldier", "Episodes"): section(
        "The Falcon and the Winter Soldier", "Episodes", episode(3, "Power Broker", "Madripoor."))})

    record = plot_record(tfatws, client, retrieved_at="t")

    assert [(e["season"], e["number_in_season"]) for e in record["episodes"]] == [(1, 3)]


def test_missing_section_gives_an_empty_record():
    record = plot_record(IRON_MAN, FakeClient({}), retrieved_at="t")
    assert record["kind"] == "" and record["sections"] == [] and record["text"] == ""


# --- wikidata_episodes --------------------------------------------------------------

def item(qid):
    return {"mainsnak": {"datavalue": {"type": "wikibase-entityid", "value": {"id": qid}}}}


def test_wikidata_episodes_reads_season_parts_directly():
    season = {"claims": {"P527": [item("E1"), item("E2")]}}
    client = FakeClient({}, {"E1": {"id": "E1", "claims": {"P31": [item("Q21191270")]}},
                             "E2": {"id": "E2", "claims": {"P31": [item("Q21191270")]}}})
    assert [e["id"] for e in wikidata_episodes(season, client)] == ["E1", "E2"]


def test_wikidata_episodes_descends_from_series_through_seasons():
    series = {"claims": {"P527": [item("S1")]}}
    client = FakeClient({}, {
        "S1": {"id": "S1", "claims": {"P31": [item("Q3464665")], "P527": [item("E1")]}},
        "E1": {"id": "E1", "claims": {"P31": [item("Q21191270")]}}})
    assert [e["id"] for e in wikidata_episodes(series, client)] == ["E1"]
