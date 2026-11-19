"""Collect Tier 1 cast from Wikidata and map TMDB people to Wikidata actors.

Input:  source_data/wikidata/entities.json (title entities saved by build_title_registry)
        TMDB person IDs from tmdb_cast
Output: source_data/wikidata/cast.csv          (cast member / voice actor + character)
        source_data/wikidata/cast_entities.json (raw actor and character labels/aliases)
        source_data/wikidata/tmdb_person_qids.csv     (TMDB person ID <-> actor QID via P4985,
                                                       for people from either source)
"""

from src.source_data_collection.build_title_registry import ENTITIES_PATH, SEASON, WIKIDATA_LICENSE
from src.source_data_collection.storage import read_json, write_csv, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.utils import claims_with_qualifier_map, label

OUTPUT_DIR = PROJECT_ROOT / "source_data" / "wikidata"
WIKIDATA_CAST_PATH = OUTPUT_DIR / "cast.csv"
CAST_ENTITIES_PATH = OUTPUT_DIR / "cast_entities.json"
PERSON_QIDS_PATH = OUTPUT_DIR / "tmdb_person_qids.csv"

# Wikidata property IDs (verified on wikidata.org 2026-11-17).
P_CAST_MEMBER = "P161"
P_VOICE_ACTOR = "P725"
P_CHARACTER_ROLE = "P453"
P_LANGUAGE_OF_WORK = "P407"
Q_ENGLISH = "Q1860"
P_TMDB_PERSON_ID = "P4985"

SPARQL_BATCH = 200
VIA_PARENT_SERIES = "parent_series"


def _provenance(qid, retrieved_at):
    return {"source": "wikidata", "source_url": f"https://www.wikidata.org/wiki/{qid}",
            "retrieved_at": retrieved_at, "license": WIKIDATA_LICENSE}


def cast_pairs(title, entity, via=""):
    """One row per (actor, character) from cast member and voice actor claims. Claims in a
    language other than English are dubs (the Russian voices of Spider-Man 2) and are skipped."""
    pairs = []
    for pid in (P_CAST_MEMBER, P_VOICE_ACTOR):
        for actor, qualifiers in claims_with_qualifier_map(entity, pid, (P_CHARACTER_ROLE, P_LANGUAGE_OF_WORK)):
            languages = qualifiers[P_LANGUAGE_OF_WORK]
            if languages and Q_ENGLISH not in languages:
                continue
            for character in qualifiers[P_CHARACTER_ROLE] or [""]:
                pairs.append({"title": title["title"], "title_qid": title["wikidata_qid"],
                              "actor_qid": actor, "character_qid": character, "property": pid,
                              "via": via})
    return pairs


def title_cast_pairs(title, entities):
    """The title's own cast; a TV season also gets its parent series' cast (via='parent_series'),
    because Wikidata records season casts on the series. Which of those actors appear in the
    season is decided later against the season's TMDB credits."""
    pairs = cast_pairs(title, entities[title["wikidata_qid"]])
    parent = title.get("parent_series_qid")
    if title.get("type") == SEASON and parent in entities:
        pairs += cast_pairs(title, entities[parent], via=VIA_PARENT_SERIES)
    return pairs


def _p4985_pairs(variable, values, client, batch_size):
    bindings = []
    for i in range(0, len(values), batch_size):
        query = f"SELECT ?actor ?tmdb WHERE {{ VALUES ?{variable} {{ " \
                f"{' '.join(values[i:i + batch_size])} }} ?actor wdt:{P_TMDB_PERSON_ID} ?tmdb }}"
        bindings += client.sparql(query)
    return bindings


def person_qid_rows(person_ids, actor_qids, client, batch_size=SPARQL_BATCH, retrieved_at=""):
    """All TMDB person ID (P4985) links for the TMDB people and Wikidata actors given.

    Looking up both sides lets validation compare the sources in both directions.
    """
    bindings = (_p4985_pairs("tmdb", [f'"{p}"' for p in person_ids], client, batch_size)
                + _p4985_pairs("actor", [f"wd:{q}" for q in actor_qids], client, batch_size))
    pairs = dict.fromkeys((b["tmdb"], b["actor"]) for b in bindings)
    return [{"tmdb_person_id": tmdb, "actor_qid": actor, **_provenance(actor, retrieved_at)}
            for tmdb, actor in pairs]


def ambiguous_person_ids(mapping_rows):
    """TMDB people linked from more than one Wikidata item (duplicates or wrong links)."""
    qids = {}
    for r in mapping_rows:
        qids.setdefault(r["tmdb_person_id"], set()).add(r["actor_qid"])
    return [p for p, q in qids.items() if len(q) > 1]


def _names(entity):
    """Label plus every English / multilingual alias."""
    aliases = [a["value"] for lang in ("en", "mul") for a in entity.get("aliases", {}).get(lang, [])]
    return list(dict.fromkeys(n for n in [label(entity), *aliases] if n))


def collect(titles, person_ids, client, retrieved_at):
    title_entities = read_json(ENTITIES_PATH)["entities"]
    pairs = [p for t in titles for p in title_cast_pairs(t, title_entities)]

    qids = list(dict.fromkeys(q for p in pairs for q in (p["actor_qid"], p["character_qid"]) if q))
    entities = client.get_entities(qids, props="labels|aliases")
    write_json(CAST_ENTITIES_PATH, {"retrieved_at": retrieved_at, "source": "wikidata",
                                    "license": WIKIDATA_LICENSE, "entities": entities})

    rows = [{**p,
             "actor_label": label(entities.get(p["actor_qid"], {})) or "",
             "character_label": label(entities.get(p["character_qid"], {})) or "",
             "character_names": "|".join(_names(entities.get(p["character_qid"], {}))),
             **_provenance(p["title_qid"], retrieved_at)}
            for p in pairs]
    write_csv(WIKIDATA_CAST_PATH, rows)

    actor_qids = list(dict.fromkeys(p["actor_qid"] for p in pairs))
    mapping = person_qid_rows(person_ids, actor_qids, client, retrieved_at=retrieved_at)
    write_csv(PERSON_QIDS_PATH, mapping)
    return rows, mapping
