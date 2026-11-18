"""Find MCU wiki (Fandom) pages for top-billed TMDB credits in MCU titles.

Many supporting MCU characters (e.g. Katy, B-15, Dar-Benn) have no Wikidata item. The MCU wiki
has a page for them whose character infobox names the actor. A page is accepted for a credit
only if that infobox lists the credit's TMDB actor, so a name search alone never decides.

Needs:  source_data/wikidata/titles.csv, source_data/tmdb/cast.csv
Output: source_data/fandom/mcu_wiki/<page>.json          (raw first section of each matched page)
        source_data/fandom/mcu_wiki_credits.csv     (credit -> matched page, or blank)
        source_data/fandom/mcu_wiki_characters.csv  (parsed infobox per matched page)
Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.collect_mcu_wiki
"""

import re

import mwparserfromhell

from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.cast_matching import distinctive_tokens, name_parts, normalize_name
from src.source_data_collection.collect_characters import FANDOM_DIR, FANDOM_LICENSE, MCU_WIKI
from src.source_data_collection.storage import read_csv, utc_now, write_csv, write_json
from src.source_data_collection.tmdb_cast import TMDB_CAST_PATH
from src.source_data_collection.wikitext import infobox_params, name_list
from src.utils import FandomClient

MCU_WIKI_RAW_DIR = FANDOM_DIR / "mcu_wiki"
MCU_WIKI_CREDITS_PATH = FANDOM_DIR / "mcu_wiki_credits.csv"
MCU_WIKI_CHARACTERS_PATH = FANDOM_DIR / "mcu_wiki_characters.csv"

MCU_UNIVERSES = {"MCU", "MCU animation"}  # tier-list universes the MCU wiki covers
MAX_BILLING = 20
SEARCH_HITS = 3
INFOBOX = "Character"


def _alias_names(value):
    """Names inside {{Alias |primary = ... |codenames = ... |nicknames = ...}}."""
    names = []
    for template in mwparserfromhell.parse(value).filter_templates(recursive=False):
        if str(template.name).strip().lower() == "alias":
            for param in template.params:
                names += name_list(str(param.value))
    return names or name_list(value)


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
            "tv_series": name_list(params.get("tv series", ""))}


def actor_matches(actor_name, infobox_actors):
    wanted = f" {normalize_name(actor_name)} "
    return any(wanted in f" {normalize_name(a)} " for a in infobox_actors)


def candidate_credits(tmdb_rows, titles, max_billing=MAX_BILLING):
    """Named, top-billed credits in MCU titles, without duplicates."""
    seen, found = set(), []
    for r in tmdb_rows:
        key = (r["title_qid"], r["tmdb_person_id"], r["character"])
        title = titles.get(r["title_qid"])
        if (key in seen or not title or title["universe"] not in MCU_UNIVERSES
                or int(r["billing_order"]) >= max_billing or not distinctive_tokens(r["character"])):
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


def _file_name(page):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", page) + ".json"


def main():
    retrieved_at = utc_now()
    titles = {t["wikidata_qid"]: t for t in read_csv(REGISTRY_PATH)}
    credits = candidate_credits(read_csv(TMDB_CAST_PATH), titles)
    client, cache = FandomClient(), {}

    credit_rows, pages = [], {}
    for i, c in enumerate(credits, 1):
        page, term = match_credit(c, client, cache)
        if page:
            pages[page["page"]] = page
        credit_rows.append({"title_qid": c["title_qid"], "tmdb_person_id": c["tmdb_person_id"],
                            "actor_name": c["actor_name"], "tmdb_character": c["character"],
                            "page": page["page"] if page else "", "search_term": term,
                            "source": "mcu_wiki", "source_url": page["url"] if page else "",
                            "retrieved_at": retrieved_at, "license": FANDOM_LICENSE})
        if i % 100 == 0:
            print(f"{i}/{len(credits)} credits searched", flush=True)

    character_rows = []
    for name, page in pages.items():
        write_json(MCU_WIKI_RAW_DIR / _file_name(name),
                   {**page, "source": "mcu_wiki", "retrieved_at": retrieved_at, "license": FANDOM_LICENSE})
        box = mcu_wiki_infobox(page["wikitext"])
        character_rows.append({"page": name, "revid": page["revid"],
                               **{k: "|".join(v) for k, v in box.items()},
                               "source": "mcu_wiki", "source_url": page["url"],
                               "retrieved_at": retrieved_at, "license": FANDOM_LICENSE})
    write_csv(MCU_WIKI_CREDITS_PATH, credit_rows)
    write_csv(MCU_WIKI_CHARACTERS_PATH, character_rows)
    matched = sum(bool(r["page"]) for r in credit_rows)
    print(f"MCU wiki: {matched}/{len(credit_rows)} credits matched to {len(pages)} pages")


if __name__ == "__main__":
    main()
