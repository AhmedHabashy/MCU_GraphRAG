"""Unit tests for src/source_data_collection/collect_mcu_wiki.py (fake client, no network)."""

from src.source_data_collection.collect_mcu_wiki import (
    actor_matches,
    candidate_credits,
    match_credit,
    mcu_wiki_infobox,
)

KATY_LEAD = """{{Character
|image = Katy.png
|real name = Katy Chen{{Ref|SCatLotTR}}<br>Chen Ruiwen{{Ref|SCatLotTR}}
|alias = {{Alias |primary = Katy |nicknames = Little Mooch{{Ref|SCatLotTR}}}}
|affiliation = [[Ta Lo]]
|movie = [[Shang-Chi and the Legend of the Ten Rings]]
|actor = [[Awkwafina]]
}}
'''Katy Chen''' is a valet."""


# --- mcu_wiki_infobox -------------------------------------------------------------------

def test_infobox_reads_names_aliases_actors_and_appearances():
    box = mcu_wiki_infobox(KATY_LEAD)
    assert box == {"real_names": ["Katy Chen", "Chen Ruiwen"], "aliases": ["Katy", "Little Mooch"],
                   "actors": ["Awkwafina"], "affiliations": ["Ta Lo"],
                   "movies": ["Shang-Chi and the Legend of the Ten Rings"], "tv_series": []}


def test_pages_without_a_character_infobox_give_none():
    assert mcu_wiki_infobox("{{Location |name = Ta Lo}}") is None


# --- actor_matches -------------------------------------------------------------------------

def test_actor_matches_ignores_case_accents_and_notes():
    assert actor_matches("Awkwafina", ["Awkwafina"])
    assert actor_matches("Ever Anderson", ["Scarlett Johansson", "Ever Anderson (young)"])
    assert actor_matches("Zoë Saldaña", ["Zoe Saldana"])
    assert not actor_matches("Owen Wilson", ["Luke Wilson"])


# --- candidate_credits ---------------------------------------------------------------------

TITLES = {"Q65768589": {"wikidata_qid": "Q65768589", "universe": "MCU", "type": "Film"},
          "Q106182": {"wikidata_qid": "Q106182", "universe": "Fox X-Men", "type": "Film"},
          "Q107185252": {"wikidata_qid": "Q107185252", "universe": "MCU", "type": "Series season"},
          "Q27089570": {"wikidata_qid": "Q27089570", "universe": "Netflix", "type": "Series"}}


def credit(title_qid, person, actor, character, order):
    return {"title_qid": title_qid, "tmdb_person_id": person, "actor_name": actor,
            "character": character, "billing_order": str(order)}


def test_candidates_are_named_top_billed_credits_in_mcu_titles():
    rows = [credit("Q65768589", "1", "Awkwafina", "Katy", 2),
            credit("Q65768589", "1", "Awkwafina", "Katy", 2),               # duplicate
            credit("Q65768589", "2", "Extra", "Additional Voices (voice)", 3),  # no name
            credit("Q65768589", "3", "Late", "Bus Driver", 40),              # billed too low
            credit("Q106182", "4", "Hugh Jackman", "Logan", 0)]             # not an MCU title
    assert [c["character"] for c in candidate_credits(rows, TITLES, max_billing=20)] == ["Katy"]


def test_series_credits_are_candidates_whatever_their_billing():
    """TMDB's series order is no measure of importance: He Who Remains is billed 550."""
    rows = [credit("Q107185252", "5", "Jonathan Majors", "He Who Remains", 550)]
    assert [c["character"] for c in candidate_credits(rows, TITLES, max_billing=20)] == ["He Who Remains"]


def test_netflix_series_are_covered():
    rows = [credit("Q27089570", "6", "Amber Rose Revah", "Dinah Madani", 4)]
    assert [c["character"] for c in candidate_credits(rows, TITLES, max_billing=20)] == ["Dinah Madani"]


# --- match_credit --------------------------------------------------------------------------

class FakeFandom:
    def __init__(self, search, pages):
        self.search_results, self.pages, self.searches = search, pages, []

    def search(self, wiki, query, limit):
        self.searches.append(query)
        return self.search_results.get(query, [])[:limit]

    def lead(self, wiki, page):
        return self.pages.get(page)


def lead(page, wikitext):
    return {"page": page, "revid": 1, "wikitext": wikitext,
            "url": f"https://marvelcinematicuniverse.fandom.com/wiki/{page}"}


def test_match_takes_the_first_hit_whose_infobox_names_the_actor():
    client = FakeFandom({"Katy": ["Katy (disambiguation)", "Katy Chen"]},
                        {"Katy (disambiguation)": lead("Katy (disambiguation)", "A list."),
                         "Katy Chen": lead("Katy Chen", KATY_LEAD)})
    page, term = match_credit(credit("Q65768589", "1", "Awkwafina", "Katy", 2), client, cache={})
    assert page["page"] == "Katy Chen" and term == "Katy"


def test_match_tries_each_name_part():
    client = FakeFandom({"Little Mooch": ["Katy Chen"]}, {"Katy Chen": lead("Katy Chen", KATY_LEAD)})
    page, term = match_credit(credit("Q65768589", "1", "Awkwafina", "Hunter / Little Mooch", 2),
                              client, cache={})
    assert page["page"] == "Katy Chen" and term == "Little Mooch"


def test_no_match_when_no_infobox_names_the_actor():
    client = FakeFandom({"Katy": ["Katy Chen"]}, {"Katy Chen": lead("Katy Chen", KATY_LEAD)})
    assert match_credit(credit("Q65768589", "9", "Someone Else", "Katy", 2), client, cache={}) == (None, "")


def test_pages_are_fetched_once_through_the_cache():
    calls = []

    class Counting(FakeFandom):
        def lead(self, wiki, page):
            calls.append(page)
            return super().lead(wiki, page)

    client = Counting({"Katy": ["Katy Chen"]}, {"Katy Chen": lead("Katy Chen", KATY_LEAD)})
    cache = {}
    match_credit(credit("Q65768589", "1", "Awkwafina", "Katy", 2), client, cache)
    match_credit(credit("Q65768589", "1", "Awkwafina", "Katy", 2), client, cache)
    assert calls == ["Katy Chen"]
