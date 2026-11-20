"""Collect Tier 1 title details: directors, writers, first release date, sequel links, locations,
and every credited actor's birth date, each with a second source for cross-checking.

"First release" is the earliest release of any kind (premieres included), as chosen for this
project. Series and seasons use their earliest episode when that is earlier or the item has none.

Needs:  build_title_registry, collect_cast, collect_plots (episode items)
Output: source_data/wikidata/title_details.csv   (directors, writers, first release, sequels, locations)
        source_data/wikidata/title_people.json   (raw labels of the people, places and titles linked)
        source_data/wikidata/actor_births.csv    (every credited actor's birth dates)
        source_data/tmdb/first_releases.csv       (TMDB's first release per title)
        source_data/tmdb/crew.csv                 (directors and writers from the saved credits)
        source_data/tmdb/person_birthdays.csv     (TMDB birthdays of the same actors)
Run:    .venv\\Scripts\\python.exe -m src.source_data_collection.collect_title_details
"""

from src.source_data_collection.build_title_registry import (
    ENTITIES_PATH, REGISTRY_PATH, WIKIDATA_LICENSE,
)
from src.source_data_collection.collect_plots import EPISODE_ENTITIES_PATH
from src.source_data_collection.incremental import TitleScopes, in_title_order, stored_rows
from src.source_data_collection.storage import read_csv, read_json, utc_now, write_csv, write_json
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.source_data_collection.tmdb_cast import (
    CREDITS_DIR, TMDB_CAST_PATH, TMDB_LICENSE, make_client,
)
from src.source_data_collection.wikidata_cast import PERSON_QIDS_PATH
from src.tmdb_client import TMDB_API
from src.utils import WikimediaClient, claim_values, claims_with_qualifiers, day_dates, label

WIKIDATA_DIR = PROJECT_ROOT / "source_data" / "wikidata"
TMDB_DIR = PROJECT_ROOT / "source_data" / "tmdb"
TITLE_DETAILS_PATH = WIKIDATA_DIR / "title_details.csv"
TITLE_PEOPLE_PATH = WIKIDATA_DIR / "title_people.json"
ACTOR_BIRTHS_PATH = WIKIDATA_DIR / "actor_births.csv"
TMDB_FIRST_RELEASES_PATH = TMDB_DIR / "first_releases.csv"
TMDB_CREW_PATH = TMDB_DIR / "crew.csv"
TMDB_BIRTHDAYS_PATH = TMDB_DIR / "person_birthdays.csv"

# Wikidata property IDs (verified on wikidata.org 2026-11-18, see validation).
P_DIRECTOR = "P57"
P_SCREENWRITER = "P58"
P_PUBLICATION_DATE = "P577"
P_START_TIME = "P580"
P_FOLLOWS = "P155"
P_FOLLOWED_BY = "P156"
P_PART_OF_THE_SERIES = "P179"
P_NARRATIVE_LOCATION = "P840"
P_BIRTH_DATE = "P569"

TMDB_CREW_ROLES = {"Directing": "director", "Writing": "writer"}


def _joined(values):
    return "|".join(dict.fromkeys(v for v in values if v))


def first_release(entity, episodes):
    """(date, from): the earliest dated release of the item or of any of its episodes."""
    own = day_dates(entity, P_PUBLICATION_DATE) + day_dates(entity, P_START_TIME)
    from_episodes = [d for e in episodes for d in day_dates(e, P_PUBLICATION_DATE)]
    candidates = [(d, "item") for d in own] + [(d, "episodes") for d in from_episodes]
    return min(candidates, default=("", ""))


def sequel_links(entity):
    """(follows, followed by) QIDs. The ordering within a series ('part of the series' with
    follows / followed-by qualifiers) is preferred; direct claims are used only without it,
    because they can disagree (e.g. X-Men Origins: Wolverine)."""
    def series_ordering(pid):
        return [q for _, qs in claims_with_qualifiers(entity, P_PART_OF_THE_SERIES, pid) for q in qs]

    scoped = {pid: series_ordering(pid) for pid in (P_FOLLOWS, P_FOLLOWED_BY)}
    if not any(scoped.values()):
        scoped = {pid: claim_values(entity, pid) for pid in (P_FOLLOWS, P_FOLLOWED_BY)}
    return list(dict.fromkeys(scoped[P_FOLLOWS])), list(dict.fromkeys(scoped[P_FOLLOWED_BY]))


def title_detail_row(title, entity, episodes, labels, retrieved_at):
    follows, followed_by = sequel_links(entity)
    date, date_from = first_release(entity, episodes)

    def qids_and_names(qids):
        return _joined(qids), _joined(labels.get(q, "") for q in qids)

    directors = qids_and_names(claim_values(entity, P_DIRECTOR))
    writers = qids_and_names(claim_values(entity, P_SCREENWRITER))
    follows_ = qids_and_names(follows)
    followed = qids_and_names(followed_by)
    locations = qids_and_names(claim_values(entity, P_NARRATIVE_LOCATION))
    return {
        "title": title["title"], "title_qid": title["wikidata_qid"], "type": title["type"],
        "director_qids": directors[0], "director_names": directors[1],
        "writer_qids": writers[0], "writer_names": writers[1],
        "first_release_date": date, "first_release_from": date_from,
        "follows_qids": follows_[0], "follows_names": follows_[1],
        "followed_by_qids": followed[0], "followed_by_names": followed[1],
        "location_qids": locations[0], "location_names": locations[1],
        "source": "wikidata", "source_url": f"https://www.wikidata.org/wiki/{title['wikidata_qid']}",
        "retrieved_at": retrieved_at, "license": WIKIDATA_LICENSE,
    }


def tmdb_crew_rows(title_qid, saved_credits):
    """Directors and writers from a saved TMDB credits response (film or aggregate TV)."""
    rows = []
    for person in saved_credits["response"].get("crew", []):
        role = TMDB_CREW_ROLES.get(person.get("department"))
        if role:
            rows.append({"title_qid": title_qid, "tmdb_person_id": str(person["id"]),
                         "name": person["name"], "role": role,
                         "source": "tmdb", "source_url": saved_credits["source_url"],
                         "retrieved_at": saved_credits["retrieved_at"],
                         "license": saved_credits["license"]})
    return rows


def _actors():
    """(TMDB person, actor QID) for every credited person with exactly one Wikidata actor."""
    qids = {}
    for r in read_csv(PERSON_QIDS_PATH):
        qids.setdefault(r["tmdb_person_id"], set()).add(r["actor_qid"])
    people = list(dict.fromkeys(r["tmdb_person_id"] for r in read_csv(TMDB_CAST_PATH)))
    return [(p, next(iter(qids[p]))) for p in people if len(qids.get(p, ())) == 1]


def main():
    retrieved_at = utc_now()
    titles = read_csv(REGISTRY_PATH)
    entities = read_json(ENTITIES_PATH)["entities"]
    episodes = read_json(EPISODE_ENTITIES_PATH)["by_title"]
    wikimedia, tmdb = WikimediaClient(), make_client()

    linked = list(dict.fromkeys(
        q for t in titles for e in [entities[t["wikidata_qid"]]]
        for q in [*claim_values(e, P_DIRECTOR), *claim_values(e, P_SCREENWRITER),
                  *claim_values(e, P_NARRATIVE_LOCATION), *(x for s in sequel_links(e) for x in s)]))
    people = wikimedia.get_entities(linked, props="labels")
    write_json(TITLE_PEOPLE_PATH, {"retrieved_at": retrieved_at, "source": "wikidata",
                                   "license": WIKIDATA_LICENSE, "entities": people})
    labels = {q: label(e) or "" for q, e in people.items()}
    write_csv(TITLE_DETAILS_PATH, [
        title_detail_row(t, entities[t["wikidata_qid"]], episodes.get(t["wikidata_qid"], []),
                         labels, retrieved_at) for t in titles])
    print(f"Wikidata: details for {len(titles)} titles, {len(people)} linked items", flush=True)

    # First releases: only new or changed titles are looked up again.
    scopes = TitleScopes("tmdb_first_releases")
    todo = scopes.to_collect(titles)
    releases = stored_rows(TMDB_FIRST_RELEASES_PATH,
                           {t["wikidata_qid"] for t in titles} - {t["wikidata_qid"] for t in todo})
    for t in todo:
        path, date = tmdb.first_release(t)
        releases.append({"title_qid": t["wikidata_qid"], "first_release_date": date,
                         "source": "tmdb", "source_url": f"{TMDB_API}{path}",
                         "retrieved_at": retrieved_at, "license": TMDB_LICENSE})
    write_csv(TMDB_FIRST_RELEASES_PATH, in_title_order(releases, titles))
    scopes.save(titles)
    write_csv(TMDB_CREW_PATH, [r for t in titles for r in tmdb_crew_rows(
        t["wikidata_qid"], read_json(CREDITS_DIR / f"{t['wikidata_qid']}.json"))])
    print("TMDB: first releases and crew", flush=True)

    actors = _actors()
    actor_entities = wikimedia.get_entities([q for _, q in actors], props="claims")
    write_csv(ACTOR_BIRTHS_PATH, [
        {"tmdb_person_id": p, "actor_qid": q,
         "birth_dates": "|".join(day_dates(actor_entities.get(q, {}), P_BIRTH_DATE)),
         "source": "wikidata", "source_url": f"https://www.wikidata.org/wiki/{q}",
         "retrieved_at": retrieved_at, "license": WIKIDATA_LICENSE} for p, q in actors])
    # Birthdays: people looked up before are kept.
    known = {r["tmdb_person_id"]: r for r in stored_rows(TMDB_BIRTHDAYS_PATH, {p for p, _ in actors},
                                                         key="tmdb_person_id")}
    write_csv(TMDB_BIRTHDAYS_PATH, [
        known.get(p) or {"tmdb_person_id": p, "birthday": tmdb.person(p).get("birthday") or "",
                         "source": "tmdb", "source_url": f"{TMDB_API}/person/{p}",
                         "retrieved_at": retrieved_at, "license": TMDB_LICENSE} for p, _ in actors])
    print(f"Birth dates for {len(actors)} actors", flush=True)


if __name__ == "__main__":
    main()
