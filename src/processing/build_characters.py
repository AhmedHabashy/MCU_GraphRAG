"""Build the merged character table: one character per reality, with aliases and variant links.

A character is (Wikidata item, reality), written "<QID>@<Earth>". The reality of a role is the
title's curated reality (docs/data_sources_and_tiers.md), unless the character item has its own
screen reality that differs (a crossover, e.g. the Raimi Green Goblin in No Way Home). Anthology
titles ("Multiverse") make every role a multiverse variant. Comics originals are characters on
Earth-616; screen characters link to them ("based_on", or "variant_of" when the role itself
points at the comics item).

Needs:  source_data (build_title_registry, collect_cast, collect_characters)
Output: processed_data/characters/characters.csv        (character_id, base item, reality, ...)
        processed_data/characters/character_aliases.csv (every name, normalized, with source)
        processed_data/characters/character_links.csv   (based_on, variant_of, same_as, different_from)
        processed_data/characters/performances.csv      (title, actor, character; Wikidata and TMDB)
Run:    .venv\\Scripts\\python.exe -m src.processing.build_characters
"""

from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.cast_matching import character_matches, name_parts, normalize_name
from src.source_data_collection.collect_characters import (
    CHARACTER_ENTITIES_PATH, CHARACTERS_PATH as COLLECTED_CHARACTERS_PATH, MARVEL_DB_PATH,
    P_FANDOM_ARTICLE_ID, SELF_QID, earth_of,
)
from src.source_data_collection.storage import read_csv, read_json, write_csv
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.source_data_collection.tmdb_cast import TMDB_CAST_PATH, TMDB_PERSON_WIKIDATA_PATH
from src.source_data_collection.wikidata_cast import PERSON_QIDS_PATH, WIKIDATA_CAST_PATH
from src.utils import claim_values, label

OUTPUT_DIR = PROJECT_ROOT / "processed_data" / "characters"
CHARACTERS_PATH = OUTPUT_DIR / "characters.csv"
ALIASES_PATH = OUTPUT_DIR / "character_aliases.csv"
LINKS_PATH = OUTPUT_DIR / "character_links.csv"
PERFORMANCES_PATH = OUTPUT_DIR / "performances.csv"

EARTH_616 = "Earth-616"
MULTIVERSE = "Multiverse"
# Wikidata universes that do not pin down one reality: the MCU franchise as a whole
# (it spans Earth-199999, Earth-828, ...) and the comics' Earth-616.
NON_SPECIFIC_UNIVERSES = {"Q642878", "Q2246088"}


def _split(value):
    return [v for v in value.split("|") if v]


def character_id(base_qid, reality):
    return f"{base_qid}@{reality}"


# --- identity ------------------------------------------------------------------------------

def resolve_actor(tmdb_person_id, qids_by_person, tmdb_pointer):
    """The actor QID for a TMDB person: the only Wikidata link, or TMDB's pick among several."""
    qids = qids_by_person.get(tmdb_person_id, set())
    if len(qids) == 1:
        return next(iter(qids))
    pick = tmdb_pointer.get(tmdb_person_id)
    return pick if pick in qids else None


def own_realities(character, universe_earths, marvel_db_earth):
    """Specific realities a character item belongs to: its Marvel Database Earth plus the
    Earths of its Wikidata universes, except the franchise-wide MCU and comics Earth-616."""
    earths = {universe_earths.get(q, "") for q in _split(character["universe_qids"])
              if q not in NON_SPECIFIC_UNIVERSES}
    return {e for e in earths | {marvel_db_earth} if e and e != EARTH_616}


def performance_reality(title_reality, own):
    """Reality of a role: the title's, unless the character has a single other own reality."""
    if title_reality == MULTIVERSE or not own or title_reality in own:
        return title_reality
    return next(iter(own)) if len(own) == 1 else title_reality


def _marvel_db_earth(qid, marvel_db):
    row = marvel_db.get(qid)
    return earth_of(row["page"]) if row and row.get("fetched") == "True" else ""


def _role_reality(title_reality, base, characters, marvel_db, universe_earths):
    own = own_realities(characters[base], universe_earths, _marvel_db_earth(base, marvel_db))
    return performance_reality(title_reality, own)


def universe_earths_from(related):
    """Wikidata universe item -> its Marvel Database Earth page (from P6262 'marvel:...')."""
    earths = {}
    for qid, entity in related.items():
        pages = [v.removeprefix("marvel:").replace("_", " ")
                 for v in claim_values(entity, P_FANDOM_ARTICLE_ID) if v.startswith("marvel:")]
        if pages:
            earths[qid] = pages[0]
    return earths


def _marvel_db_names(row):
    return [n for n in [row["name"], row["current_alias"], *_split(row["other_names"])] if n]


def _names(character, marvel_db_row=None):
    """Wikidata names of a character, plus its Marvel Database names if given."""
    names = [character["label"], *_split(character["aliases"]), *_split(character["pseudonyms"]),
             *_split(character["birth_names"])]
    return [n for n in names if n] + (_marvel_db_names(marvel_db_row) if marvel_db_row else [])


def _performance(title_qid, actor_qid, actor_name, base_qid, cid, source, method,
                 tmdb_person_id="", tmdb_character="", billing_order=""):
    return {"title_qid": title_qid, "actor_qid": actor_qid or "", "tmdb_person_id": tmdb_person_id,
            "actor_name": actor_name, "base_qid": base_qid, "character_id": cid,
            "tmdb_character": tmdb_character, "billing_order": billing_order,
            "link_method": method, "source": source}


def wikidata_performances(cast, titles, characters, marvel_db, universe_earths):
    """One performance per Wikidata cast role that names a character."""
    rows = []
    for r in cast:
        base = r["character_qid"]
        if not base or base == SELF_QID or base not in characters or r["title_qid"] not in titles:
            continue
        reality = _role_reality(titles[r["title_qid"]]["reality"], base, characters, marvel_db,
                                universe_earths)
        rows.append(_performance(r["title_qid"], r["actor_qid"], r["actor_label"], base,
                                 character_id(base, reality), "wikidata", "wikidata"))
    return rows


def link_tmdb_credits(tmdb_rows, wikidata_perfs, qids_by_person, tmdb_pointer, titles,
                      characters, marvel_db, universe_earths):
    """Attach each TMDB credit to a character via its actor: the actor's role in that title
    (by name if several), else a role the actor plays in another title whose name matches."""
    by_title_actor, by_actor = {}, {}
    for p in wikidata_perfs:
        by_title_actor.setdefault((p["title_qid"], p["actor_qid"]), []).append(p)
        by_actor.setdefault(p["actor_qid"], set()).add(p["base_qid"])

    def matching(bases, credit):
        return [b for b in bases
                if character_matches(credit["character"], _names(characters[b], marvel_db.get(b)))]

    rows = []
    for credit in tmdb_rows:
        actor = resolve_actor(credit["tmdb_person_id"], qids_by_person, tmdb_pointer)
        same_title = by_title_actor.get((credit["title_qid"], actor), [])
        cid, base, method = "", "", ""
        if len({p["character_id"] for p in same_title}) == 1:
            cid, base, method = same_title[0]["character_id"], same_title[0]["base_qid"], "same_title"
        elif same_title:
            hits = matching({p["base_qid"] for p in same_title}, credit)
            if len(hits) == 1:
                base, method = hits[0], "same_title_name"
                cid = next(p["character_id"] for p in same_title if p["base_qid"] == base)
        elif actor in by_actor and credit["title_qid"] in titles:
            hits = matching(by_actor[actor], credit)
            if len(hits) == 1:
                base, method = hits[0], "other_title_name"
                cid = character_id(base, _role_reality(titles[credit["title_qid"]]["reality"],
                                                       base, characters, marvel_db, universe_earths))
        rows.append(_performance(credit["title_qid"], actor, credit["actor_name"], base, cid,
                                 "tmdb", method, credit["tmdb_person_id"], credit["character"],
                                 credit["billing_order"]))
    return rows


# --- characters, aliases and links ----------------------------------------------------------

def _entity_names(entity):
    aliases = [a["value"] for lang in ("en", "mul") for a in entity.get("aliases", {}).get(lang, [])]
    return [n for n in [label(entity), *aliases] if n]


def character_rows(performances, characters, marvel_db, related):
    """Character, alias and link rows for every character used in a performance."""
    nodes, aliases, links = {}, {}, []

    def add_alias(cid, name, source):
        key = (cid, normalize_name(name), source)
        if key[1] and key not in aliases:
            aliases[key] = {"character_id": cid, "alias": name, "normalized": key[1], "source": source}

    def add_original(qid):
        """Comics original (Earth-616) node; returns its id and label."""
        cid = character_id(qid, EARTH_616)
        item = characters.get(qid)
        names = _names(item) if item else _entity_names(related.get(qid, {}))
        if cid not in nodes:
            nodes[cid] = {"character_id": cid, "base_qid": qid, "reality": EARTH_616,
                          "label": names[0] if names else qid, "is_comics_original": True,
                          "based_on_qids": "", "marvel_db_page": "", "titles": set()}
            for n in names:
                add_alias(cid, n, "wikidata")
        return cid, nodes[cid]["label"]

    for p in performances:
        if not p["character_id"]:
            continue
        cid, base = p["character_id"], p["base_qid"]
        item = characters[base]
        reality = cid.rsplit("@", 1)[1]
        if cid not in nodes:
            mdb = marvel_db.get(base)
            mdb_matches = mdb and _marvel_db_earth(base, marvel_db) == reality
            nodes[cid] = {"character_id": cid, "base_qid": base, "reality": reality,
                          "label": item["label"], "is_comics_original": False,
                          "based_on_qids": item["based_on_qids"],
                          "marvel_db_page": mdb["page"] if mdb_matches else "", "titles": set()}
            for n in _names(item):
                add_alias(cid, n, "wikidata")
            if mdb_matches:
                for n in _marvel_db_names(mdb):
                    add_alias(cid, n, "marvel_database")
            for qid, qlabel in zip(_split(item["based_on_qids"]), _split(item["based_on_labels"])):
                to_id, _ = add_original(qid)
                links.append(_link(cid, "based_on", qid, to_id, qlabel))
            if EARTH_616 in _split(item["universe_earths"]) and reality != EARTH_616:
                to_id, to_label = add_original(base)
                links.append(_link(cid, "variant_of", base, to_id, to_label))
            for qid in _split(item["same_as_qids"]):
                links.append(_link(cid, "same_as", qid, "", label(related.get(qid, {})) or ""))
            for qid, qlabel in zip(_split(item["different_from_qids"]),
                                   _split(item["different_from_labels"])):
                links.append(_link(cid, "different_from", qid, "", qlabel))
        nodes[cid]["titles"].add(p["title_qid"])
        for n in name_parts(p["tmdb_character"]):
            add_alias(cid, n, "tmdb")

    rows = [{**n, "titles": len(n["titles"]), "source": "derived"} for n in nodes.values()]
    return rows, list(aliases.values()), links


def _link(from_id, relation, to_qid, to_id, to_label):
    return {"from_id": from_id, "relation": relation, "to_qid": to_qid, "to_id": to_id,
            "to_label": to_label, "source": "wikidata"}


def main():
    titles = {t["wikidata_qid"]: t for t in read_csv(REGISTRY_PATH)}
    characters = {r["character_qid"]: r for r in read_csv(COLLECTED_CHARACTERS_PATH)}
    marvel_db = {r["character_qid"]: r for r in read_csv(MARVEL_DB_PATH)}
    related = read_json(CHARACTER_ENTITIES_PATH)["related"]
    qids_by_person = {}
    for r in read_csv(PERSON_QIDS_PATH):
        qids_by_person.setdefault(r["tmdb_person_id"], set()).add(r["actor_qid"])
    tmdb_pointer = {r["tmdb_person_id"]: r["wikidata_id"] for r in read_csv(TMDB_PERSON_WIKIDATA_PATH)}

    universe_earths = universe_earths_from(related)

    wikidata = wikidata_performances(read_csv(WIKIDATA_CAST_PATH), titles, characters, marvel_db,
                                     universe_earths)
    tmdb = link_tmdb_credits(read_csv(TMDB_CAST_PATH), wikidata, qids_by_person, tmdb_pointer,
                             titles, characters, marvel_db, universe_earths)
    performances = wikidata + tmdb
    rows, aliases, links = character_rows(performances, characters, marvel_db, related)

    write_csv(PERFORMANCES_PATH, performances)
    write_csv(CHARACTERS_PATH, rows)
    write_csv(ALIASES_PATH, aliases)
    write_csv(LINKS_PATH, links)
    linked = sum(bool(p["character_id"]) for p in tmdb)
    print(f"{len(rows)} characters, {len(aliases)} aliases, {len(links)} links; "
          f"TMDB credits linked {linked}/{len(tmdb)}")


if __name__ == "__main__":
    main()
