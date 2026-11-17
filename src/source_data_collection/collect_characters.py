"""Collect Tier 1 characters: names, aliases, universes and variant links.

Characters are the Wikidata character roles in the Tier 1 cast. For each, Wikidata gives
names, universe (P1080), the comics character it is based on (P144) and same-as /
different-from links; the Marvel Database (Fandom) infobox gives names, aliases, reality
and affiliations, as an independent second source.

Needs:  source_data/wikidata/tier1_cast.csv (collect_cast)
Output: source_data/wikidata/tier1_characters.csv          (one row per character)
        source_data/wikidata/tier1_character_entities.json (raw characters + linked items)
        source_data/fandom/marvel_database/<QID>.json      (raw infobox section, as collected)
        source_data/fandom/tier1_marvel_database.csv       (parsed infobox fields)
Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.collect_characters
"""

import re

from src.source_data_collection.build_title_registry import WIKIDATA_LICENSE
from src.source_data_collection.storage import read_csv, utc_now, write_csv, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.source_data_collection.wikidata_cast import WIKIDATA_CAST_PATH
from src.source_data_collection.wikitext import infobox_params, name_list, plain_text
from src.utils import FandomClient, WikimediaClient, claim_values, fandom_url, label

WIKIDATA_DIR = PROJECT_ROOT / "source_data" / "wikidata"
CHARACTERS_PATH = WIKIDATA_DIR / "tier1_characters.csv"
CHARACTER_ENTITIES_PATH = WIKIDATA_DIR / "tier1_character_entities.json"
FANDOM_DIR = PROJECT_ROOT / "source_data" / "fandom"
MARVEL_DB_RAW_DIR = FANDOM_DIR / "marvel_database"
MARVEL_DB_PATH = FANDOM_DIR / "tier1_marvel_database.csv"

FANDOM_LICENSE = "CC BY-SA 3.0"
MARVEL_DB_WIKI = "marvel"
MARVEL_DB_TEMPLATE = "Marvel Database:Character Template"
SELF_QID = "Q18086706"  # generic "self" item used for people playing themselves

# Wikidata property IDs (verified on wikidata.org 2026-11-17).
P_NARRATIVE_UNIVERSE = "P1080"
P_BASED_ON = "P144"
P_SAME_AS = "P460"
P_DIFFERENT_FROM = "P1889"
P_FANDOM_ARTICLE_ID = "P6262"
P_PSEUDONYM = "P742"
P_BIRTH_NAME = "P1477"
P_PERFORMER = "P175"
# Linked items fetched for labels: universes and identity links. Comics originals (P144) are
# out of scope for now; their IDs are kept only as a key for grouping screen variants.
LINK_PROPERTIES = (P_NARRATIVE_UNIVERSE, P_SAME_AS, P_DIFFERENT_FROM)
MARVEL_DB_COMICS_EARTH = "Earth-616"  # the Marvel Database's comics universe

_EARTH = re.compile(r"\((Earth-[^)]+)\)$")


def character_qids(cast_rows):
    return list(dict.fromkeys(r["character_qid"] for r in cast_rows
                              if r["character_qid"] and r["character_qid"] != SELF_QID))


def _fandom_pages(entity, wiki):
    prefix = f"{wiki}:"
    return [v[len(prefix):].replace("_", " ") for v in claim_values(entity, P_FANDOM_ARTICLE_ID)
            if v.startswith(prefix)]


def marvel_db_page(entity):
    pages = _fandom_pages(entity, MARVEL_DB_WIKI)
    return pages[0] if pages else ""


def earth_of(page):
    match = _EARTH.search(page)
    return match.group(1) if match else ""


def wants_marvel_db_page(page):
    """Screen-character pages only; comics (Earth-616 on the Marvel Database) are skipped."""
    return bool(page) and earth_of(page) != MARVEL_DB_COMICS_EARTH


def linked_qids(entities):
    return list(dict.fromkeys(q for e in entities.values() for p in LINK_PROPERTIES
                              for q in claim_values(e, p)))


def _texts(entity, pid):
    """String values; monolingual text claims (e.g. pseudonym) give their text."""
    return [v["text"] if isinstance(v, dict) else v for v in claim_values(entity, pid)]


def _aliases(entity):
    return [a["value"] for lang in ("en", "mul") for a in entity.get("aliases", {}).get(lang, [])]


def _joined(values):
    return "|".join(dict.fromkeys(v for v in values if v))


def character_row(entity, related, retrieved_at):
    qid = entity["id"]
    universes = claim_values(entity, P_NARRATIVE_UNIVERSE)

    def labels(pid):
        return _joined(label(related.get(q, {})) or "" for q in claim_values(entity, pid))

    return {
        "character_qid": qid,
        "label": label(entity) or "",
        "aliases": _joined(_aliases(entity)),
        "pseudonyms": _joined(_texts(entity, P_PSEUDONYM)),
        "birth_names": _joined(_texts(entity, P_BIRTH_NAME)),
        "universe_qids": _joined(universes),
        "universe_labels": labels(P_NARRATIVE_UNIVERSE),
        "universe_earths": _joined(p for u in universes
                                   for p in _fandom_pages(related.get(u, {}), MARVEL_DB_WIKI)),
        "based_on_qids": _joined(claim_values(entity, P_BASED_ON)),
        "same_as_qids": _joined(claim_values(entity, P_SAME_AS)),
        "different_from_qids": _joined(claim_values(entity, P_DIFFERENT_FROM)),
        "different_from_labels": labels(P_DIFFERENT_FROM),
        "performer_qids": _joined(claim_values(entity, P_PERFORMER)),
        "marvel_db_page": marvel_db_page(entity),
        "source": "wikidata",
        "source_url": f"https://www.wikidata.org/wiki/{qid}",
        "retrieved_at": retrieved_at,
        "license": WIKIDATA_LICENSE,
    }


def marvel_db_row(character_qid, lead, retrieved_at, page=""):
    """Parsed Marvel Database infobox; blank fields if the page was missing."""
    params = infobox_params(lead["wikitext"], MARVEL_DB_TEMPLATE) if lead else {}
    names = [n for field in ("Codenames", "Titles", "Nicknames", "Aliases")
             for n in name_list(params.get(field, ""))]
    return {
        "character_qid": character_qid,
        "page": lead["page"] if lead else page,
        "fetched": lead is not None,
        "revid": lead["revid"] if lead else "",
        "name": plain_text(params.get("Name", "")),
        "current_alias": plain_text(params.get("CurrentAlias", "")),
        "other_names": _joined(names),
        "reality": _joined(name_list(params.get("Reality", ""))),
        "affiliations": _joined(name_list(params.get("Affiliation", ""))),
        "source": "marvel_database",
        "source_url": lead["url"] if lead else fandom_url(MARVEL_DB_WIKI, page),
        "retrieved_at": retrieved_at,
        "license": FANDOM_LICENSE,
    }


def main():
    retrieved_at = utc_now()
    wikimedia, fandom = WikimediaClient(), FandomClient()

    qids = character_qids(read_csv(WIKIDATA_CAST_PATH))
    entities = wikimedia.get_entities(qids, props="labels|aliases|descriptions|claims")
    related = wikimedia.get_entities(linked_qids(entities), props="labels|aliases|claims")
    write_json(CHARACTER_ENTITIES_PATH, {"retrieved_at": retrieved_at, "source": "wikidata",
                                         "license": WIKIDATA_LICENSE,
                                         "characters": entities, "related": related})
    rows = [character_row(entities[q], related, retrieved_at) for q in qids if q in entities]
    write_csv(CHARACTERS_PATH, rows)
    print(f"Wikidata: {len(rows)} characters, {len(related)} linked items", flush=True)

    marvel_rows = []
    for row in rows:
        if not wants_marvel_db_page(row["marvel_db_page"]):
            continue
        lead = fandom.lead(MARVEL_DB_WIKI, row["marvel_db_page"])
        if lead:
            write_json(MARVEL_DB_RAW_DIR / f"{row['character_qid']}.json",
                       {**lead, "character_qid": row["character_qid"], "source": "marvel_database",
                        "retrieved_at": retrieved_at, "license": FANDOM_LICENSE})
        marvel_rows.append(marvel_db_row(row["character_qid"], lead, retrieved_at,
                                         page=row["marvel_db_page"]))
    write_csv(MARVEL_DB_PATH, marvel_rows)
    print(f"Marvel Database: {sum(r['fetched'] for r in marvel_rows)}/{len(marvel_rows)} "
          f"pages fetched", flush=True)


if __name__ == "__main__":
    main()
