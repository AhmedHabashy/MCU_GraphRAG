"""Find MCU wiki (Fandom) pages for TMDB credits in MCU titles: top-billed film credits and
every named series credit (TMDB's series order says nothing about importance: guest stars,
e.g. He Who Remains in Loki, are billed after the extras).

Many supporting MCU characters (e.g. Katy, B-15, Dar-Benn) have no Wikidata item. The MCU wiki
has a page for them whose character infobox names the actor. A page is accepted for a credit
only if that infobox lists the credit's TMDB actor, so a name search alone never decides.

Pages that Wikidata declares for a collected character (e.g. Iron Man) are kept too, even when
no credit matched them; "requested_page" is the declared name, which may redirect to "page".

Needs:  source_data/wikidata/titles.csv, source_data/tmdb/cast.csv, source_data/wikidata/characters.csv
Output: source_data/fandom/mcu_wiki/<page>.json          (raw first section of each kept page)
        source_data/fandom/mcu_wiki_credits.csv     (credit -> matched page, or blank)
        source_data/fandom/mcu_wiki_characters.csv  (parsed infobox per kept page)
Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.collect_mcu_wiki
"""

import re

import mwparserfromhell

from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.cast_matching import distinctive_tokens, name_parts, normalize_name
from src.source_data_collection.collect_characters import (
    CHARACTERS_PATH as WIKIDATA_CHARACTERS_PATH, FANDOM_DIR, FANDOM_LICENSE, MCU_WIKI,
)
from src.source_data_collection.storage import read_csv, read_json, utc_now, write_csv, write_json
from src.source_data_collection.tmdb_cast import TMDB_CAST_PATH
from src.source_data_collection.wikitext import infobox_params, name_list, plain_text
from src.title_types import is_movie
from src.utils import FandomClient

MCU_WIKI_RAW_DIR = FANDOM_DIR / "mcu_wiki"
MCU_WIKI_CREDITS_PATH = FANDOM_DIR / "mcu_wiki_credits.csv"
MCU_WIKI_CHARACTERS_PATH = FANDOM_DIR / "mcu_wiki_characters.csv"

MCU_UNIVERSES = {"MCU", "MCU animation", "Netflix", "Marvel TV", "ABC"}  # tier-list universes the MCU wiki covers
MAX_BILLING = 20  # films only
SEARCH_HITS = 3
INFOBOX = "Character"
NOT_OWN_ALIASES = {"undercover"}  # Alias fields naming people the character posed as
NOT_OWN_SPECIES = {"formerly", "temporarily", "framework"}  # a species with this note is not the character's own
NOT_SPECIES = {"hybrid", "glossary"}  # links that qualify a species instead of naming one


def _alias_names(value):
    """Names inside {{Alias |primary = ... |codenames = ... |nicknames = ...}}, except the
    'undercover' identities: those are people the character posed as (Talos as Nick Fury)."""
    names = []
    for template in mwparserfromhell.parse(value).filter_templates(recursive=False):
        if str(template.name).strip().lower() == "alias":
            for param in template.params:
                if str(param.name).strip().lower() not in NOT_OWN_ALIASES:
                    names += name_list(str(param.value))
    return names or name_list(value)


def species_names(value):
    """Species in an infobox 'species' value, one entry per line: the linked names shown (or
    the plain text when nothing is linked), without notes, references or comments. A line whose
    note is (formerly), (temporarily) or (Framework) is not the character's own species."""
    names = []
    for line in re.split(r"<br\s*/?>|\n", value, flags=re.IGNORECASE):
        code = mwparserfromhell.parse(line)
        notes = [t for t in code.filter_tags(recursive=False) if str(t.tag).lower() in ("small", "ref")]
        if any(plain_text(str(n.contents or "")).strip(" ()").lower() in NOT_OWN_SPECIES
               for n in notes if str(n.tag).lower() == "small"):
            continue
        for node in [*notes, *code.filter_comments(recursive=False), *code.filter_templates(recursive=False)]:
            code.remove(node)
        links = [l for l in code.filter_wikilinks(recursive=False)
                 if str(l.title).split("#")[0].strip().lower() not in NOT_SPECIES]
        shown = [plain_text(str(l.text if l.text else l.title)) for l in links] or [plain_text(str(code))]
        names += [n for n in shown if n and n not in names]
    return names


def mcu_wiki_infobox(wikitext):
    """Parsed character infobox, or None if the page has none."""
    params = infobox_params(wikitext, INFOBOX)
    if not params:
        return None
    return {"real_names": name_list(params.get("real name", "")),
            "aliases": _alias_names(params.get("alias", "")),
            "actors": name_list(params.get("actor", "")),
            "affiliations": name_list(params.get("affiliation", "")),
            "movies": name_list(params.get("movie", "")),
            "tv_series": name_list(params.get("tv series", "")),
            "species": species_names(params.get("species", ""))}


def actor_matches(actor_name, infobox_actors):
    wanted = f" {normalize_name(actor_name)} "
    return any(wanted in f" {normalize_name(a)} " for a in infobox_actors)


def candidate_credits(tmdb_rows, titles, max_billing=MAX_BILLING):
    """Named credits in MCU titles, top-billed for films, without duplicates."""
    seen, found = set(), []
    for r in tmdb_rows:
        key = (r["title_qid"], r["tmdb_person_id"], r["character"])
        title = titles.get(r["title_qid"])
        if (key in seen or not title or title["universe"] not in MCU_UNIVERSES
                or (is_movie(title) and int(r["billing_order"]) >= max_billing)
                or not distinctive_tokens(r["character"])):
            continue
        seen.add(key)
        found.append(r)
    return found


def match_credit(credit, client, cache):
    """(page lead, search term) of the first hit whose infobox names the credit's actor."""
    for term in name_parts(credit["character"]):
        if not distinctive_tokens(term):
            continue
        for hit in client.search(MCU_WIKI, term, limit=SEARCH_HITS):
            if hit not in cache:
                cache[hit] = client.lead(MCU_WIKI, hit)
            page = cache[hit]
            box = mcu_wiki_infobox(page["wikitext"]) if page else None
            if box and actor_matches(credit["actor_name"], box["actors"]):
                return page, term
    return None, ""


def credit_key(row):
    """A stored credit row's key: (title, TMDB person, TMDB character)."""
    return row["title_qid"], row["tmdb_person_id"], row["tmdb_character"]


def declared_pages(wikidata_characters, collected):
    """MCU wiki pages Wikidata declares for its characters that are not collected yet."""
    names = dict.fromkeys(r["mcu_wiki_page"].replace("_", " ") for r in wikidata_characters)
    return [n for n in names if n and n not in collected]


def _file_name(page):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", page) + ".json"


def main():
    retrieved_at = utc_now()
    titles = {t["wikidata_qid"]: t for t in read_csv(REGISTRY_PATH)}
    credits = candidate_credits(read_csv(TMDB_CAST_PATH), titles)
    client, cache = FandomClient(), {}

    # Credits searched before keep their stored row and page; only new credits are searched.
    stored = {credit_key(r): r for r in read_csv(MCU_WIKI_CREDITS_PATH)} if MCU_WIKI_CREDITS_PATH.exists() else {}
    credit_rows, pages, searched = [], {}, 0
    for c in credits:
        row = stored.get((c["title_qid"], c["tmdb_person_id"], c["character"]))
        if row:
            if row["page"] and row["page"] not in pages:
                pages[row["page"]] = read_json(MCU_WIKI_RAW_DIR / _file_name(row["page"]))
            credit_rows.append(row)
            continue
        page, term = match_credit(c, client, cache)
        if page:
            pages[page["page"]] = {**page, "source": "mcu_wiki", "retrieved_at": retrieved_at,
                                   "license": FANDOM_LICENSE}
            write_json(MCU_WIKI_RAW_DIR / _file_name(page["page"]), pages[page["page"]])
        credit_rows.append({"title_qid": c["title_qid"], "tmdb_person_id": c["tmdb_person_id"],
                            "actor_name": c["actor_name"], "tmdb_character": c["character"],
                            "page": page["page"] if page else "", "search_term": term,
                            "source": "mcu_wiki", "source_url": page["url"] if page else "",
                            "retrieved_at": retrieved_at, "license": FANDOM_LICENSE})
        searched += 1
        if searched % 100 == 0:
            print(f"{searched} new credits searched", flush=True)

    # Declared pages saved before are read back; only new ones are fetched.
    missing = []
    for name in declared_pages(read_csv(WIKIDATA_CHARACTERS_PATH), pages):
        path = MCU_WIKI_RAW_DIR / _file_name(name)
        if path.exists():
            pages[name] = read_json(path)
            continue
        page = client.lead(MCU_WIKI, name)
        if not page:
            missing.append(name)
            continue
        pages[name] = {**page, "source": "mcu_wiki", "retrieved_at": retrieved_at, "license": FANDOM_LICENSE}
        write_json(path, pages[name])
    if missing:
        print(f"WARNING: {len(missing)} pages declared by Wikidata do not exist: {missing}")

    character_rows = []
    for name, page in pages.items():
        box = mcu_wiki_infobox(page["wikitext"])
        if box is None:
            print(f"WARNING: {name} has no character infobox; skipped")
            continue
        character_rows.append({"page": page["page"], "requested_page": name, "revid": page["revid"],
                               **{k: "|".join(v) for k, v in box.items()},
                               "source": "mcu_wiki", "source_url": page["url"],
                               "retrieved_at": page["retrieved_at"], "license": FANDOM_LICENSE})
    write_csv(MCU_WIKI_CREDITS_PATH, credit_rows)
    write_csv(MCU_WIKI_CHARACTERS_PATH, character_rows)
    matched = sum(bool(r["page"]) for r in credit_rows)
    print(f"MCU wiki: {matched}/{len(credit_rows)} credits matched to {len(pages)} pages "
          f"({searched} credits searched now)")


if __name__ == "__main__":
    main()
