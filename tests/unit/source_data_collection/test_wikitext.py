"""Unit tests for src/source_data_collection/wikitext.py."""

from src.source_data_collection.wikitext import (
    episode_entries,
    infobox_params,
    member_links,
    name_list,
    plain_text,
    transcluded_pages,
)


# --- plain_text -----------------------------------------------------------------

def test_plain_text_keeps_link_display_text_and_drops_markup():
    wikitext = ("== Plot ==\n[[Loki (Marvel Cinematic Universe)|Loki]] is arrested in 2012."
                "{{efn|As in ''[[Avengers: Endgame]]''}} The [[Time Variance Authority]]"
                "<ref name=a>{{cite web|title=x}}</ref> resets the ''Sacred'' timeline."
                "<!-- hidden note -->")
    assert plain_text(wikitext) == \
        "Loki is arrested in 2012. The Time Variance Authority resets the Sacred timeline."


def test_plain_text_keeps_paragraph_breaks():
    assert plain_text("First paragraph.\n\nSecond  paragraph.") == \
        "First paragraph.\n\nSecond paragraph."


# --- episode_entries ------------------------------------------------------------

EPISODE_TABLE = """<onlyinclude>{{Episode table |background=#754925 |episodes=
{{Episode list/sublist|Loki season 1
 |EpisodeNumber   = 1
 |EpisodeNumber2  = 1
 |Title           = [[Glorious Purpose (Loki season 1)|Glorious Purpose]]
 |OriginalAirDate = {{Start date|2021|6|9}}
 |ShortSummary    = [[Loki (Marvel Cinematic Universe)|Loki]] is arrested by the TVA.
}}
{{Episode list/sublist|Loki season 1
 |EpisodeNumber   = 2
 |EpisodeNumber2  = 2
 |Title           = The Variant
 |OriginalAirDate = {{Start date|2021|6|16}}
 |ShortSummary    = Mobius recruits Loki.
}}
}}</onlyinclude>"""


def test_episode_entries_read_each_episode_list_template():
    episodes = episode_entries(EPISODE_TABLE)

    assert [(e["number_overall"], e["number_in_season"], e["title"], e["air_date"])
            for e in episodes] == [(1, 1, "Glorious Purpose", "2021-06-09"),
                                   (2, 2, "The Variant", "2021-06-16")]
    assert episodes[0]["summary_text"] == "Loki is arrested by the TVA."
    assert "[[Loki (Marvel Cinematic Universe)|Loki]]" in episodes[0]["summary_wikitext"]


def test_episode_entries_use_episode_number_when_there_is_no_season_number():
    wikitext = """{{Episode list
 |EpisodeNumber = 3
 |Title = Power Broker
 |OriginalAirDate = {{Start date|2021|4|2}}
 |ShortSummary = Sam and Bucky go to Madripoor.
}}"""
    episode = episode_entries(wikitext)[0]
    assert (episode["number_overall"], episode["number_in_season"]) == (3, 3)


def test_multi_part_entry_with_numbered_parts_gives_one_episode_per_part():
    wikitext = """{{Episode list/sublist|X-Men '97 season 1
 |EpisodeNumber_1 = 8
 |EpisodeNumber2_1 = 8
 |EpisodeNumber_2 = 9
 |EpisodeNumber2_2 = 9
 |Title = Tolerance Is Extinction
 |OriginalAirDate_1 = {{Start date|2024|05|01}}
 |OriginalAirDate_2 = {{Start date|2024|05|08}}
 |ShortSummary = Bastion attacks.
 |NumParts = 2
}}"""
    episodes = episode_entries(wikitext)

    assert [(e["number_overall"], e["number_in_season"], e["title"], e["air_date"],
             e["part"], e["num_parts"], e["summary_text"]) for e in episodes] == [
        (8, 8, "Tolerance Is Extinction", "2024-05-01", 1, 2, "Bastion attacks."),
        (9, 9, "Tolerance Is Extinction", "2024-05-08", 2, 2, "Bastion attacks.")]


def test_multi_part_entry_with_one_number_is_one_episode_with_joined_titles():
    wikitext = """{{Episode list/sublist|X-Men '97 season 1
 |EpisodeNumber = 4
 |EpisodeNumber2 = 4
 |Title_1 = Motendo
 |Title_2 = Lifedeath – Part 1
 |OriginalAirDate = {{Start date|2024|04|03}}
 |ShortSummary = Jubilee and Roberto are trapped in a game.
 |NumParts = 2
}}"""
    [episode] = episode_entries(wikitext)

    assert (episode["number_in_season"], episode["title"], episode["part"], episode["num_parts"]) \
        == (4, "Motendo / Lifedeath – Part 1", 1, 1)


def test_single_episode_is_part_one_of_one():
    episode = episode_entries("{{Episode list |EpisodeNumber = 1 |Title = A }}")[0]
    assert (episode["part"], episode["num_parts"]) == (1, 1)


def test_untitled_episodes_use_the_raw_title_field():
    """Wikipedia uses RTitle for titles shown without quotation marks, e.g. 'Episode 1'."""
    episode = episode_entries("{{Episode list |EpisodeNumber = 1 |RTitle = Episode 1 }}")[0]
    assert episode["title"] == "Episode 1"


def test_episode_entries_leave_missing_fields_blank():
    episode = episode_entries("{{Episode list |EpisodeNumber = 4 |Title = TBA }}")[0]
    assert episode["summary_text"] == "" and episode["air_date"] == ""


# --- infobox_params / name_list --------------------------------------------------

LEAD = """{{Otheruses}}
{{Marvel Database:Character Template
| Name     = [[Tony Stark|Anthony Edward "Tony" Stark]]
| CurrentAlias = Iron Man
| Aliases  = * Howard Potts{{r|Avengers: Endgame}} * The Mechanic{{r|Iron Man 3 (film)}}
| Reality  = [[Earth-199999]]
| Empty    =
}}
'''Tony Stark''' was a billionaire."""


def test_infobox_params_reads_the_named_template_only():
    params = infobox_params(LEAD, "Marvel Database:Character Template")
    assert params["CurrentAlias"] == "Iron Man"
    assert params["Reality"] == "[[Earth-199999]]"
    assert "Empty" not in params


def test_infobox_params_is_empty_without_the_template():
    assert infobox_params("{{Otheruses}} text", "Marvel Database:Character Template") == {}


def test_infobox_params_survive_markup_that_breaks_the_rest_of_the_page():
    """MCU wiki Daredevil: an unclosed italic inside a reference plus an italic later in the
    article made the whole-page parse drop the infobox."""
    lead = ("{{Character\n|real name = Matt Murdock\n|IDno = 1<ref>[https://a.b ''Lot #65]</ref>\n}}\n"
            "On the ''Northern Star''.")
    assert infobox_params(lead, "Character")["real name"] == "Matt Murdock"


def test_infobox_params_survive_a_stray_italic_inside_the_template():
    """MCU wiki Punisher: ''Title'' - x]'' in a reference made 'real name' swallow the rest."""
    lead = ("{{Character\n|real name = Frank<ref>[https://a.b ''The Punisher'' - Graves]''</ref> "
            "<small>(birth name)</small>\n|species = [[Human]]\n|comic = ''[[Born Again]]'' <small>(mentioned)</small>\n}}")
    params = infobox_params(lead, "Character")
    assert params["species"] == "[[Human]]" and params["comic"].startswith("''[[Born Again]]''")


def test_infobox_params_match_the_whole_template_name():
    assert infobox_params("{{CharHub|A|B}}{{Character|name = A}}", "Character") == {"name": "A"}


def test_name_list_splits_bullets_breaks_and_commas_and_drops_refs():
    assert name_list("* Howard Potts{{r|Avengers: Endgame}} * The Mechanic{{r|x}}") == \
        ["Howard Potts", "The Mechanic"]
    assert name_list("Logan, Weapon X<br>Patch; ''Jim''") == ["Logan", "Weapon X", "Patch", "Jim"]


def test_name_list_drops_references_and_comments_before_splitting():
    """MCU wiki values: a comma inside a reference or comment is not a list separator."""
    assert name_list('Swoll Groot<ref>[https://x.y James Gunn on Twitter - November 25, 2022]</ref>'
                     '<br>Groot') == ["Swoll Groot", "Groot"]
    assert name_list('Timothy Cadwallader Dugan<!--- Credits for "Timothy", SSR File --->') == \
        ["Timothy Cadwallader Dugan"]
    assert name_list('Loki <ref>{{ConjectureRef|Name, see talk}}</ref>') == ["Loki"]
    assert name_list('Hoskins<ref group="note">Unknown which parent, if any</ref>') == ["Hoskins"]
    assert name_list('Soul Vision<ref name="a"/>') == ["Soul Vision"]


def test_name_list_drops_notes():
    """MCU wiki notes such as <small>(birth name)</small> describe a name; they are not part of it."""
    assert name_list("Francis David Castle <small>(birth name)</small><br>Peter Castiglione "
                     "<small>(legal name)</small>") == ["Francis David Castle", "Peter Castiglione"]
    assert name_list("[[Charlie Cox]]<br>[[Skylar Gaertner]] <small>(young)</small>") == \
        ["Charlie Cox", "Skylar Gaertner"]


def test_name_list_keeps_link_template_text_and_drops_status_prefixes():
    """{{m|Page}} / {{m|Page|Shown}} is the Marvel Database link template."""
    assert name_list("Formerly: * {{m|Avengers}} * [[X-Men]] * {{m|Strategic Homeland|S.H.I.E.L.D.}}") \
        == ["Avengers", "X-Men", "S.H.I.E.L.D."]


# --- member_links ---------------------------------------------------------------

def test_member_links_keep_page_display_name_and_former_status():
    value = ("*[[Charles Xavier (Earth-10005)|Professor X]] Formerly: "
             "*[[Raven Darkhölme (Earth-10005)|Mystique]] (field leader) "
             "*[[Henry McCoy (Earth-10005)|Beast]]{{r|X-Men: First Class}}")
    assert member_links(value) == [
        {"page": "Charles Xavier (Earth-10005)", "name": "Professor X", "former": False},
        {"page": "Raven Darkhölme (Earth-10005)", "name": "Mystique", "former": True},
        {"page": "Henry McCoy (Earth-10005)", "name": "Beast", "former": True}]


def test_member_links_read_mcu_wiki_lists_with_line_breaks_and_refs():
    value = "[[Thor Odinson]]<ref>[https://ign.com x]</ref><br>[[Sam Wilson]]<br>[[Bucky Barnes]]"
    assert [m["page"] for m in member_links(value)] == ["Thor Odinson", "Sam Wilson", "Bucky Barnes"]
    assert member_links("[[Sue Storm]]")[0] == {"page": "Sue Storm", "name": "Sue Storm", "former": False}


def test_member_links_read_links_inside_italic_and_bold_text():
    value = "''[[Captain Marvel (film)|Captain Marvel]]''<ref>[[Ignored]]</ref> '''[[Iron Man 2]]'''"
    assert [m["page"] for m in member_links(value)] == ["Captain Marvel (film)", "Iron Man 2"]


def test_member_links_ignore_links_inside_notes_and_references():
    value = "* [[Lucas Bishop (Earth-31393)|Bishop]] <small>(from [[Earth-31393]])</small><ref>[[Ignored]]</ref>"
    assert [m["page"] for m in member_links(value)] == ["Lucas Bishop (Earth-31393)"]


# --- transcluded_pages ----------------------------------------------------------

def test_transcluded_pages_lists_pages_pulled_in_with_colon_syntax():
    wikitext = ("=== Season 1 (2021) ===\n{{Main|What If...? season 1}}\n"
                "{{:What If...? season 1}}\n=== Season 2 ===\n{{:What If...? season 2}}")
    assert transcluded_pages(wikitext) == ["What If...? season 1", "What If...? season 2"]
