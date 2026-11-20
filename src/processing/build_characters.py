"""Build the merged character table for films and series: one character per reality,
with aliases and variant links. Comics are out of scope for now.

A character is (identity, reality), written "<identity>@<Earth>"; the main MCU is Earth-616
(see realities.py). The identity is a Wikidata QID, or "mcuwiki:<Page>" for a supporting
character that only the MCU wiki covers (accepted only when its infobox names the actor).

The reality of a role is the title's curated reality (docs/data_sources_and_tiers.md), unless
the character has a single other specific reality (a crossover, e.g. the Raimi Green Goblin in
No Way Home). Anthology titles ("Multiverse") make every role a multiverse variant.

TMDB credits are linked to characters in this order:
  same_title / same_title_name  the actor's Wikidata role in the title (by name if several)
  parent_series                 a TV season's role from its parent series' cast
  other_title_name              a role the actor plays in another title, matched by name
  performer                     a Wikidata character performed by the actor, matched by name
  mcu_wiki_qid / mcu_wiki       the verified MCU wiki page (its Wikidata item if it has one, the
                                character the lead actor's credits show the page belongs to, or
                                the one character it names among several the credit matched)

Screen characters are linked as variants when they share an item (e.g. Magneto in the Fox
films and in X-Men '97) or the item they are based on (Fox Logan and the X-Men '97 Wolverine).

Needs:  source_data (build_title_registry, collect_cast, collect_characters, collect_mcu_wiki)
Output: processed_data/characters/characters.csv        (character_id, identity, reality, label)
        processed_data/characters/character_aliases.csv (every name, normalized, with source)
        processed_data/characters/character_links.csv   (variant, same_as, different_from)
        processed_data/characters/performances.csv      (title, actor, character; Wikidata and TMDB)
Run:    .venv\\Scripts\\python.exe -m src.processing.build_characters
"""

from dataclasses import dataclass, replace
from itertools import combinations

from src.processing.curated_roles import (
    apply_curated_roles, drop_roles, load_curated_roles, load_dropped_roles, unmatched_rows,
)
from src.processing.realities import reality_of_marvel_db_earth
from src.source_data_collection.build_title_registry import REGISTRY_PATH
from src.source_data_collection.cast_matching import character_matches, name_parts, normalize_name
from src.source_data_collection.collect_characters import (
    CHARACTER_ENTITIES_PATH, CHARACTERS_PATH as COLLECTED_CHARACTERS_PATH, MARVEL_DB_PATH,
    SELF_QID, earth_of, is_marvel_screen_item, is_screen_universe, universe_pages_from,
)
from src.source_data_collection.collect_mcu_wiki import MCU_WIKI_CHARACTERS_PATH, MCU_WIKI_CREDITS_PATH
from src.source_data_collection.storage import read_csv, read_json, write_csv
from src.source_data_collection.tier_titles import PROJECT_ROOT
from src.source_data_collection.tmdb_cast import TMDB_CAST_PATH, TMDB_PERSON_WIKIDATA_PATH
from src.source_data_collection.wikidata_cast import PERSON_QIDS_PATH, WIKIDATA_CAST_PATH
from src.utils import label

OUTPUT_DIR = PROJECT_ROOT / "processed_data" / "characters"
CHARACTERS_PATH = OUTPUT_DIR / "characters.csv"
ALIASES_PATH = OUTPUT_DIR / "character_aliases.csv"
LINKS_PATH = OUTPUT_DIR / "character_links.csv"
PERFORMANCES_PATH = OUTPUT_DIR / "performances.csv"

MULTIVERSE = "Multiverse"
MCU_FRANCHISE_UNIVERSE = "Q642878"  # Wikidata's "Marvel Cinematic Universe": the whole franchise
MCU_WIKI_PREFIX = "mcuwiki:"


@dataclass(frozen=True)
class Sources:
    """Collected data the table is built from."""
    titles: dict           # title QID -> registry row (with curated reality)
    characters: dict       # character QID -> collected Wikidata character row
    marvel_db: dict        # character QID -> Marvel Database row
    related: dict          # QID -> raw Wikidata entity (universes, same-as / different-from targets)
    universe_pages: dict   # universe QID -> Marvel Database Earth page name
    mcu_credits: dict      # (title QID, TMDB person, TMDB character) -> verified MCU wiki page
    mcu_characters: dict   # MCU wiki page (as requested) -> parsed infobox row
    screen_realities: frozenset = None  # realities of films and series (None: no filter)
    mcu_pages: dict = None  # MCU wiki page -> character QID, inferred from credits (inferred_mcu_pages)

    def qid_of_mcu_page(self, page):
        """The character whose MCU wiki page this is: given by Wikidata, else inferred."""
        wanted = page.replace("_", " ")
        return next((q for q, c in self.characters.items()
                     if c["mcu_wiki_page"].replace("_", " ") == wanted), None) or (self.mcu_pages or {}).get(wanted)

    def mcu_page_of(self, qid):
        """A character's MCU wiki page: given by Wikidata, else inferred."""
        declared = self.characters[qid]["mcu_wiki_page"].replace("_", " ")
        return declared or next((p for p, q in (self.mcu_pages or {}).items() if q == qid), "")


def _split(value):
    return [v for v in value.split("|") if v]


def character_id(identity, reality):
    return f"{identity}@{reality}"


def mcu_wiki_identity(page):
    return MCU_WIKI_PREFIX + page.replace(" ", "_")


# --- identity and reality ------------------------------------------------------------------

def resolve_actor(tmdb_person_id, qids_by_person, tmdb_pointer):
    """The actor QID for a TMDB person: the only Wikidata link, or TMDB's pick among several."""
    qids = qids_by_person.get(tmdb_person_id, set())
    if len(qids) == 1:
        return next(iter(qids))
    pick = tmdb_pointer.get(tmdb_person_id)
    return pick if pick in qids else None


def own_realities(character, universe_pages, marvel_db_earth, known_realities=None):
    """Specific realities of a character item: the Earths of its Wikidata universes and its
    Marvel Database Earth (both Marvel Database page names), except the franchise-wide MCU.
    Comics are mapped away by reality_of_marvel_db_earth. If `known_realities` is given, only
    those count: a universe or page can be a video-game reality (e.g. Jubilee's Earth-30847)."""
    earths = {universe_pages.get(q, "") for q in _split(character["universe_qids"])
              if q != MCU_FRANCHISE_UNIVERSE} | {marvel_db_earth}
    own = {r for r in map(reality_of_marvel_db_earth, earths) if r}
    return own if known_realities is None else own & known_realities


def performance_reality(title_reality, own):
    """Reality of a role: the title's, unless the character has a single other own reality."""
    if title_reality == MULTIVERSE or not own or title_reality in own:
        return title_reality
    return next(iter(own)) if len(own) == 1 else title_reality


def _marvel_db_earth(qid, marvel_db):
    row = marvel_db.get(qid)
    return earth_of(row["page"]) if row and row.get("fetched") == "True" else ""


def _role_id(title_qid, identity, src):
    """character_id of an identity's role in a title."""
    title_reality = src.titles[title_qid]["reality"]
    item = src.characters.get(identity)
    own = own_realities(item, src.universe_pages, _marvel_db_earth(identity, src.marvel_db),
                        src.screen_realities) if item else set()
    return character_id(identity, performance_reality(title_reality, own))


def _marvel_db_names(row):
    return [n for n in [row["name"], row["current_alias"], *_split(row["other_names"])] if n]


def _mcu_wiki_names(row):
    return [*_split(row["real_names"]), *_split(row["aliases"])]


def _names(identity, src):
    """Every known name of a Wikidata character or an MCU wiki character."""
    if identity.startswith(MCU_WIKI_PREFIX):
        row = src.mcu_characters.get(identity.removeprefix(MCU_WIKI_PREFIX).replace("_", " "))
        return _mcu_wiki_names(row) if row else []
    item = src.characters[identity]
    names = [item["label"], *_split(item["aliases"]), *_split(item["pseudonyms"]),
             *_split(item["birth_names"])]
    if identity in src.marvel_db:
        names += _marvel_db_names(src.marvel_db[identity])
    return [n for n in names if n]


# --- performances ----------------------------------------------------------------------------

def _performance(title_qid, actor_qid, actor_name, identity, cid, source, method, via="",
                 tmdb_person_id="", tmdb_character="", billing_order=""):
    return {"title_qid": title_qid, "actor_qid": actor_qid or "", "tmdb_person_id": tmdb_person_id,
            "actor_name": actor_name, "base_qid": identity, "character_id": cid,
            "tmdb_character": tmdb_character, "billing_order": billing_order,
            "link_method": method, "via": via, "source": source}


def wikidata_roles(cast, src):
    """One role per Wikidata cast row naming a character; parent-series rows keep via='parent_series'."""
    rows = []
    for r in cast:
        base = r["character_qid"]
        if not base or base == SELF_QID or base not in src.characters or r["title_qid"] not in src.titles:
            continue
        rows.append(_performance(r["title_qid"], r["actor_qid"], r["actor_label"], base,
                                 _role_id(r["title_qid"], base, src), "wikidata", "wikidata",
                                 via=r["via"]))
    return rows


def link_tmdb_credits(tmdb_rows, roles, qids_by_person, tmdb_pointer, src):
    """Attach each TMDB credit to a character (see the module docstring for the order)."""
    by_title_actor, by_actor, performed_by = {}, {}, {}
    for r in roles:
        by_title_actor.setdefault((r["title_qid"], r["actor_qid"]), []).append(r)
        if not r["via"]:
            by_actor.setdefault(r["actor_qid"], set()).add(r["base_qid"])
    for qid, item in src.characters.items():
        for actor in _split(item["performer_qids"]):
            performed_by.setdefault(actor, set()).add(qid)
    names_played = {}  # (title, TMDB person) -> every name credited (a voice actor's other parts)
    for credit in tmdb_rows:
        names_played.setdefault((credit["title_qid"], credit["tmdb_person_id"]), set()).update(
            normalize_name(n) for n in name_parts(credit["character"]))

    def by_name(identities, credit):
        return [i for i in identities if character_matches(credit["character"], _names(i, src))]

    def link(credit, actor):
        title = credit["title_qid"]
        same_title = by_title_actor.get((title, actor), [])
        if len({r["character_id"] for r in same_title}) == 1:
            role = same_title[0]
            # The only role takes the credit, unless the actor is credited under several names
            # here and this credit names something else (Ross Marquand: Professor X, and
            # 'Apocalypse (voice)'). A credit with no name names nothing else.
            if (len(names_played[(title, credit["tmdb_person_id"])]) <= 1 or not name_parts(credit["character"])
                    or character_matches(credit["character"], _names(role["base_qid"], src))):
                return role["base_qid"], role["character_id"], "parent_series" if role["via"] else "same_title"
        ambiguous = []  # the credit names several of the actor's characters ('Kraglin / On-Set Rocket')
        if same_title:
            hits = by_name({r["base_qid"] for r in same_title}, credit)
            if len(hits) == 1:
                return hits[0], next(r["character_id"] for r in same_title if r["base_qid"] == hits[0]), \
                    "same_title_name"
            ambiguous += hits
        if title not in src.titles:
            return "", "", ""
        for method, candidates in (("other_title_name", by_actor.get(actor, set())),
                                   ("performer", performed_by.get(actor, set()))):
            hits = by_name(candidates, credit)
            if len(hits) == 1:
                return hits[0], _role_id(title, hits[0], src), method
            ambiguous += hits
        page = src.mcu_credits.get((title, credit["tmdb_person_id"], credit["character"]))
        if page:
            named = {i for i in ambiguous if character_matches(page.replace("_", " "), _names(i, src))}
            qid = src.qid_of_mcu_page(page) or (next(iter(named)) if len(named) == 1 else None)
            identity = qid or mcu_wiki_identity(page)
            cid = next((r["character_id"] for r in same_title if r["base_qid"] == identity), None)
            return identity, cid or _role_id(title, identity, src), "mcu_wiki_qid" if qid else "mcu_wiki"
        return "", "", ""

    rows = []
    for credit in tmdb_rows:
        actor = resolve_actor(credit["tmdb_person_id"], qids_by_person, tmdb_pointer)
        identity, cid, method = link(credit, actor)
        rows.append(_performance(credit["title_qid"], actor, credit["actor_name"], identity, cid,
                                 "tmdb", method, tmdb_person_id=credit["tmdb_person_id"],
                                 tmdb_character=credit["character"],
                                 billing_order=credit["billing_order"]))
    return rows


def inferred_mcu_pages(roles, mcu_credits, qids_by_person, characters):
    """MCU wiki page -> character QID, for characters Wikidata gives no page. When an actor's
    credit in a title matched page P and the actor has exactly one Wikidata role in that title,
    P is that role's character (Mike Colter's credits match 'Luke Cage', and his role is the
    comics Luke Cage item). Kept only when every such credit agrees on the character."""
    roles_of = {}
    for r in roles:
        if not r["via"]:
            roles_of.setdefault((r["title_qid"], r["actor_qid"]), set()).add(r["base_qid"])
    votes = {}
    for (title_qid, person, _), page in mcu_credits.items():
        for actor in qids_by_person.get(person, ()):
            found = roles_of.get((title_qid, actor), set())
            if len(found) == 1:
                votes.setdefault(page.replace("_", " "), set()).update(found)
    return {page: next(iter(qids)) for page, qids in votes.items()
            if len(qids) == 1 and next(iter(qids)) in characters
            and not characters[next(iter(qids))]["mcu_wiki_page"]}


def merge_comics_roles(performances, src):
    """Within one reality, a role pointing at a comics item becomes the screen character that is
    based on it, when exactly one such character has a role in that reality (e.g. Thunderbolts*
    points at the comics Yelena Belova, Black Widow at the MCU one). Other realities stay variants.
    Runs after curation, so curated realities count (No Way Home's Doc Ock is Spider-Man 2's),
    and an identity the expert set is never merged away."""
    def is_screen(qid):
        item = src.characters.get(qid)
        return bool(item) and any(is_screen_universe(u, src.universe_pages)
                                  for u in _split(item["universe_qids"]))

    based_on_in_reality = {}
    for p in performances:
        if p["character_id"] and is_screen(p["base_qid"]):
            reality = p["character_id"].rsplit("@", 1)[1]
            for original in _split(src.characters[p["base_qid"]]["based_on_qids"]):
                based_on_in_reality.setdefault((reality, original), set()).add(p["base_qid"])

    merged = []
    for p in performances:
        p = {**p, "merged_from": "", "data_base_qid": p.get("data_base_qid") or p["base_qid"]}
        if p["character_id"] and p["base_qid"] in src.characters and not is_screen(p["base_qid"])                 and not p.get("curated_identity"):
            reality = p["character_id"].rsplit("@", 1)[1]
            screen = based_on_in_reality.get((reality, p["base_qid"]), set())
            if len(screen) == 1:
                target = next(iter(screen))
                p.update(merged_from=p["base_qid"], base_qid=target,
                         character_id=character_id(target, reality))
        merged.append(p)
    return merged


# --- characters, aliases and links ----------------------------------------------------------

def _link(from_id, relation, to_id="", to_qid="", to_label="", shared_qid=""):
    return {"from_id": from_id, "relation": relation, "to_id": to_id, "to_qid": to_qid,
            "to_label": to_label, "shared_qid": shared_qid, "source": "wikidata"}


def _node(cid, identity, src):
    """Character row plus its (name, source) aliases."""
    reality = cid.rsplit("@", 1)[1]
    if identity.startswith(MCU_WIKI_PREFIX):
        page = identity.removeprefix(MCU_WIKI_PREFIX).replace("_", " ")
        row = src.mcu_characters.get(page, {"real_names": "", "aliases": ""})
        names = _mcu_wiki_names(row)
        matchable = [n for n in names if normalize_name(n)]  # not e.g. 中島依 alone
        node = {"label": matchable[0] if matchable else page, "identity_source": "mcu_wiki",
                "marvel_db_page": "", "mcu_wiki_page": page}
        return node, [(n, "mcu_wiki") for n in [page, *names]]

    item = src.characters[identity]
    mdb = src.marvel_db.get(identity)
    mdb_matches = bool(mdb) and reality_of_marvel_db_earth(_marvel_db_earth(identity, src.marvel_db)) == reality
    mcu_page = src.mcu_page_of(identity)
    names = [(n, "wikidata") for n in [item["label"], *_split(item["aliases"]),
                                       *_split(item["pseudonyms"]), *_split(item["birth_names"])]]
    if mdb_matches:
        names += [(n, "marvel_database") for n in _marvel_db_names(mdb)]
    if mcu_page in src.mcu_characters:
        names += [(n, "mcu_wiki") for n in _mcu_wiki_names(src.mcu_characters[mcu_page])]
    node = {"label": item["label"], "identity_source": "wikidata",
            "marvel_db_page": mdb["page"] if mdb_matches else "", "mcu_wiki_page": mcu_page}
    return node, names


def credit_aliases(tmdb_character, names):
    """Names a TMDB credit adds to its character. A single name is kept (it may be one no other
    source has); of several ('Cyclops / Russian Judge') only those naming the character are."""
    parts = name_parts(tmdb_character)
    return parts if len(parts) == 1 else [p for p in parts if character_matches(p, names)]


def species_of(row, known):
    """A page's species, '|'-joined; a plural name ("Humans") becomes its known singular."""
    names = [n[:-1] if n.endswith("s") and n[:-1] in known else n for n in _split(row.get("species", ""))]
    return "|".join(dict.fromkeys(names))


def character_rows(performances, src):
    """Character, alias and link rows for every character used in a performance."""
    nodes, aliases = {}, {}
    known_species = {s for r in src.mcu_characters.values() for s in _split(r.get("species", ""))}

    def add_alias(cid, name, source):
        key = (cid, normalize_name(name), source)
        if key[1] and key not in aliases:
            aliases[key] = {"character_id": cid, "alias": name, "normalized": key[1], "source": source}

    for p in performances:
        cid, identity = p["character_id"], p["base_qid"]
        if not cid:
            continue
        if cid not in nodes:
            node, names = _node(cid, identity, src)
            nodes[cid] = {"character_id": cid, "base_qid": identity,
                          "reality": cid.rsplit("@", 1)[1], **node,
                          "species": species_of(src.mcu_characters.get(node["mcu_wiki_page"], {}), known_species),
                          "titles": set(), "variant_of": set()}
            for name, source in names:
                add_alias(cid, name, source)
        if p.get("curated_label"):
            nodes[cid]["label"] = p["curated_label"]
            add_alias(cid, p["curated_label"], "curated")
        if p.get("curated_variant_of"):
            nodes[cid]["variant_of"].add(p["curated_variant_of"])
        nodes[cid]["titles"].add(p["title_qid"])
        for name in credit_aliases(p["tmdb_character"], _names(identity, src)):
            add_alias(cid, name, "tmdb")

    links = _variant_links(nodes, src) + _identity_links(nodes, src)
    rows = [{**{k: v for k, v in n.items() if k != "variant_of"}, "titles": len(n["titles"]),
             "source": "derived"} for n in nodes.values()]
    return rows, list(aliases.values()), links


def _variant_links(nodes, src):
    """Link characters in different realities that share an identity, a based-on item, or a
    curated 'variant of' character."""
    groups = {}
    for cid, node in nodes.items():
        identity = node["base_qid"]
        item = src.characters.get(identity, {"based_on_qids": ""})
        for key in [identity, *_split(item["based_on_qids"]), *node["variant_of"]]:
            groups.setdefault(key, set()).add(cid)
    pairs = {}
    for key, ids in groups.items():
        for a, b in combinations(sorted(ids), 2):
            pairs.setdefault((a, b), key)
    return [_link(a, "variant", to_id=b, shared_qid=key) for (a, b), key in sorted(pairs.items())]


def _identity_links(nodes, src):
    """Wikidata same-as / different-from links whose target is a screen character."""
    links = []
    for cid, node in nodes.items():
        item = src.characters.get(node["base_qid"])
        if not item:
            continue
        for relation, qids in (("same_as", _split(item["same_as_qids"])),
                               ("different_from", _split(item["different_from_qids"]))):
            for qid in qids:
                target = src.related.get(qid, {})
                if is_marvel_screen_item(target, src.universe_pages):
                    links.append(_link(cid, relation, to_qid=qid, to_label=label(target) or ""))
    return links


def screen_realities(titles, curated):
    """Realities a role may have: the titles' and the curated roles' realities. A role only
    leaves its title's reality for one of these (see own_realities)."""
    realities = {t["reality"] for t in titles.values()} | {r["reality"] for r in curated}
    return frozenset(r for r in realities if r)


def load_sources(curated):
    related = read_json(CHARACTER_ENTITIES_PATH)["related"]
    titles = {t["wikidata_qid"]: t for t in read_csv(REGISTRY_PATH)}
    universe_pages = universe_pages_from(related)
    return Sources(
        titles=titles,
        characters={r["character_qid"]: r for r in read_csv(COLLECTED_CHARACTERS_PATH)},
        marvel_db={r["character_qid"]: r for r in read_csv(MARVEL_DB_PATH)},
        related=related,
        universe_pages=universe_pages,
        mcu_credits={(r["title_qid"], r["tmdb_person_id"], r["tmdb_character"]): r["page"]
                     for r in read_csv(MCU_WIKI_CREDITS_PATH) if r["page"]},
        mcu_characters={r["requested_page"]: r for r in read_csv(MCU_WIKI_CHARACTERS_PATH)},
        screen_realities=screen_realities(titles, curated),
    )


def main():
    curated = load_curated_roles()
    src = load_sources(curated)
    qids_by_person = {}
    for r in read_csv(PERSON_QIDS_PATH):
        qids_by_person.setdefault(r["tmdb_person_id"], set()).add(r["actor_qid"])
    tmdb_pointer = {r["tmdb_person_id"]: r["wikidata_id"] for r in read_csv(TMDB_PERSON_WIKIDATA_PATH)}

    roles = wikidata_roles(read_csv(WIKIDATA_CAST_PATH), src)
    src = replace(src, mcu_pages=inferred_mcu_pages(roles, src.mcu_credits, qids_by_person, src.characters))
    tmdb = link_tmdb_credits(read_csv(TMDB_CAST_PATH), roles, qids_by_person, tmdb_pointer, src)
    performances = [r for r in roles if not r["via"]] + tmdb  # parent-series roles count via TMDB
    title_qids = {t["title"]: q for q, t in src.titles.items()}
    dropped = load_dropped_roles()
    unmatched = unmatched_rows(performances, dropped, title_qids)
    if unmatched:
        print(f"WARNING: {len(unmatched)} dropped roles match no performance: "
              f"{[(r['title'], r['actor']) for r in unmatched]}")
    performances = drop_roles(performances, dropped, title_qids)
    performances = apply_curated_roles(performances, curated, title_qids,
                                       {q: t["reality"] for q, t in src.titles.items()})
    performances = merge_comics_roles(performances, src)
    unmatched = unmatched_rows(performances, curated, title_qids)
    if unmatched:
        print(f"WARNING: {len(unmatched)} curated roles match no performance: "
              f"{[(r['title'], r['actor']) for r in unmatched]}")
    rows, aliases, links = character_rows(performances, src)

    write_csv(PERFORMANCES_PATH, performances)
    write_csv(CHARACTERS_PATH, rows)
    write_csv(ALIASES_PATH, aliases)
    write_csv(LINKS_PATH, links)
    linked = sum(bool(p["character_id"]) for p in tmdb)
    print(f"{len(rows)} characters, {len(aliases)} aliases, {len(links)} links; "
          f"TMDB credits linked {linked}/{len(tmdb)}")


if __name__ == "__main__":
    main()
