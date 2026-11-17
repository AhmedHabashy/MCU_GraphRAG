"""Collect Tier 1 cast credits from TMDB.

Output: source_data/tmdb/credits/<title QID>.json      (raw TMDB responses, as collected)
        source_data/tmdb/tier1_cast.csv                (one row per actor-character credit)
        source_data/tmdb/person_external_ids.csv       (TMDB's own Wikidata ID, for top-billed
                                                        and ambiguously mapped people)

Needs TMDB_API_KEY in .env.
"""

from dotenv import dotenv_values

from src.source_data_collection.cast_matching import character_flags
from src.source_data_collection.storage import write_csv, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.tmdb_client import TMDB_API, TmdbClient

OUTPUT_DIR = PROJECT_ROOT / "source_data" / "tmdb"
CREDITS_DIR = OUTPUT_DIR / "credits"
TMDB_CAST_PATH = OUTPUT_DIR / "tier1_cast.csv"
TMDB_PERSON_WIKIDATA_PATH = OUTPUT_DIR / "person_external_ids.csv"

TMDB_LICENSE = "TMDB API terms of use (attribution required)"
TOP_BILLED = 10


def _row(title, path, person, character, episode_count, retrieved_at):
    return {
        "title": title["title"], "title_qid": title["wikidata_qid"],
        "tmdb_person_id": str(person["id"]), "actor_name": person["name"],
        "character": character, "billing_order": person["order"],
        "episode_count": episode_count, **character_flags(character),
        "source": "tmdb", "source_url": f"{TMDB_API}{path}",
        "retrieved_at": retrieved_at, "license": TMDB_LICENSE,
    }


def cast_rows(title, path, payload, retrieved_at):
    """Flatten movie credits (one character) or aggregate TV credits (roles list)."""
    rows = []
    for person in payload["cast"]:
        if "roles" in person:
            rows += [_row(title, path, person, role["character"], role["episode_count"],
                          retrieved_at) for role in person["roles"]]
        else:
            rows.append(_row(title, path, person, person["character"], "", retrieved_at))
    return rows


def top_billed_person_ids(rows, limit=TOP_BILLED):
    return list(dict.fromkeys(r["tmdb_person_id"] for r in rows
                              if int(r["billing_order"]) < limit))


def collect(titles, client, retrieved_at):
    rows = []
    for title in titles:
        path, payload = client.credits(title)
        write_json(CREDITS_DIR / f"{title['wikidata_qid']}.json",
                   {"title": title["title"], "source_url": f"{TMDB_API}{path}",
                    "retrieved_at": retrieved_at, "license": TMDB_LICENSE, "response": payload})
        rows += cast_rows(title, path, payload, retrieved_at)
    write_csv(TMDB_CAST_PATH, rows)
    return rows


def external_id_rows(person_ids, client, retrieved_at):
    """TMDB's own Wikidata / IMDb IDs for each person (an independent check on P4985)."""
    rows = []
    for person_id in person_ids:
        ids = client.person_external_ids(person_id)
        rows.append({"tmdb_person_id": person_id, "wikidata_id": ids.get("wikidata_id") or "",
                     "imdb_id": ids.get("imdb_id") or "", "source": "tmdb",
                     "source_url": f"{TMDB_API}/person/{person_id}/external_ids",
                     "retrieved_at": retrieved_at, "license": TMDB_LICENSE})
    return rows


def collect_external_ids(person_ids, client, retrieved_at):
    rows = external_id_rows(person_ids, client, retrieved_at)
    write_csv(TMDB_PERSON_WIKIDATA_PATH, rows)
    return rows


def make_client():
    api_key = dotenv_values(PROJECT_ROOT / ".env").get("TMDB_API_KEY")
    if not api_key:
        raise RuntimeError("TMDB_API_KEY is missing from .env")
    return TmdbClient(api_key=api_key)
