"""Helpers for reading and checking data against Wikipedia / Wikidata endpoints."""

import time

import requests

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
ENWIKI_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
ENTITY_URI_PREFIX = "http://www.wikidata.org/entity/"
USER_AGENT = "MCU-GraphRAG/0.1 (personal research project; python-requests)"

BATCH_SIZE = 50          # MediaWiki limit for ids/titles per request
MAX_ATTEMPTS = 5
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Wikidata property IDs used in this module (verified on wikidata.org 2026-11-17).
P_PUBLICATION_DATE = "P577"
P_START_TIME = "P580"


# --- pure helpers on Wikidata entity JSON -----------------------------------

def _best_rank_claims(claims):
    """Wikidata 'truthy' semantics: preferred claims if any, else normal; never deprecated."""
    preferred = [c for c in claims if c.get("rank") == "preferred"]
    return preferred or [c for c in claims if c.get("rank", "normal") == "normal"]


def _snak_value(snak):
    """Item ID for item snaks, raw value otherwise; None for novalue/somevalue snaks."""
    datavalue = snak.get("datavalue")
    if datavalue is None:
        return None
    value = datavalue["value"]
    return value["id"] if datavalue["type"] == "wikibase-entityid" else value


def _best_claims(entity, pid):
    return _best_rank_claims(entity.get("claims", {}).get(pid, []))


def claim_values(entity, pid):
    """Best-rank values for `pid`: item IDs for item claims, raw value otherwise."""
    values = (_snak_value(c["mainsnak"]) for c in _best_claims(entity, pid))
    return [v for v in values if v is not None]


def claims_with_qualifiers(entity, pid, qualifier_pid):
    """[(value, [qualifier values])] for every best-rank `pid` claim that has a value."""
    pairs = []
    for claim in _best_claims(entity, pid):
        value = _snak_value(claim["mainsnak"])
        if value is None:
            continue
        snaks = claim.get("qualifiers", {}).get(qualifier_pid, [])
        pairs.append((value, [q for q in map(_snak_value, snaks) if q is not None]))
    return pairs


def qualifier_value(entity, pid, qualifier_pid):
    """(value, first qualifier value) of the first best-rank `pid` claim; None where absent."""
    pairs = claims_with_qualifiers(entity, pid, qualifier_pid)
    if not pairs:
        return None, None
    value, qualifiers = pairs[0]
    return value, (qualifiers[0] if qualifiers else None)


def label(entity):
    """English label, falling back to Wikidata's multilingual default ('mul')."""
    labels = entity.get("labels", {})
    for lang in ("en", "mul"):
        if lang in labels:
            return labels[lang]["value"]
    return None


def earliest_year(entity):
    """Earliest year from publication dates (P577), falling back to start time (P580)."""
    for pid in (P_PUBLICATION_DATE, P_START_TIME):
        years = [int(v["time"][1:5]) for v in claim_values(entity, pid)]
        if years:
            return min(years)
    return None


def enwiki_url(page):
    return f"https://en.wikipedia.org/wiki/{page.replace(' ', '_')}"


def fandom_url(wiki, page):
    return f"https://{wiki}.fandom.com/wiki/{page.replace(' ', '_')}"


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# --- HTTP clients -------------------------------------------------------------

class JsonHttpClient:
    """GET JSON with retry on rate limiting / server errors (honours Retry-After).

    `session` and `sleep` are injected so tests can run without the network.
    Error messages name only the URL, never the parameters, which may hold secrets.
    """

    def __init__(self, session=None, sleep=time.sleep):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.sleep = sleep

    def get_json(self, url, params):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            response = self.session.get(url, params=params, timeout=30)
            if response.status_code < 400:
                return response.json()
            if response.status_code not in RETRYABLE_STATUS:
                raise RuntimeError(f"{url} returned HTTP {response.status_code}")
            if attempt == MAX_ATTEMPTS:
                break
            self.sleep(float(response.headers.get("Retry-After", 2 ** attempt)))
        raise RuntimeError(f"{url} still failing after {MAX_ATTEMPTS} attempts "
                           f"(last status {response.status_code})")


class FandomClient(JsonHttpClient):
    """Client for Fandom wikis (MediaWiki API at https://<wiki>.fandom.com/api.php)."""

    def search(self, wiki, query, limit):
        """Titles of the top full-text search hits."""
        found = self.get_json(f"https://{wiki}.fandom.com/api.php", {
            "action": "query", "list": "search", "srsearch": query, "srlimit": limit,
            "format": "json"})
        return [hit["title"] for hit in found["query"]["search"]]

    def lead(self, wiki, page):
        """Wikitext of the page's first section (where infoboxes live), or None if missing."""
        parsed = self.get_json(f"https://{wiki}.fandom.com/api.php", {
            "action": "parse", "page": page.replace("_", " "), "prop": "wikitext|revid",
            "section": 0, "redirects": 1, "format": "json"})
        if "error" in parsed:
            return None
        title = parsed["parse"]["title"]
        return {"page": title, "revid": parsed["parse"]["revid"],
                "wikitext": parsed["parse"]["wikitext"]["*"], "url": fandom_url(wiki, title)}


class WikimediaClient(JsonHttpClient):
    """Client for the en.wikipedia and Wikidata APIs and the Wikidata SPARQL endpoint."""

    def sparql(self, query):
        """Run a SPARQL SELECT; entity URIs are shortened to their ID."""
        bindings = self.get_json(WIKIDATA_SPARQL, {"format": "json", "query": query})
        return [{name: cell["value"].removeprefix(ENTITY_URI_PREFIX)
                 for name, cell in row.items()}
                for row in bindings["results"]["bindings"]]

    def top_level_section(self, page, prefix):
        """Top-level section of `page` whose heading starts with `prefix`, or None.

        `prefix` may be a tuple; earlier prefixes win over page order. The wikitext
        is read from the same revision as the section list, and its revid returned.
        """
        parsed = self.get_json(ENWIKI_API, {"action": "parse", "page": page,
                                            "prop": "sections|revid",
                                            "redirects": 1, "format": "json"})["parse"]
        top = [s for s in parsed["sections"] if s["toclevel"] == 1]
        prefixes = (prefix,) if isinstance(prefix, str) else prefix
        section = next((s for p in prefixes for s in top if s["line"].startswith(p)), None)
        if section is None:
            return None
        text = self.get_json(ENWIKI_API, {"action": "parse", "oldid": parsed["revid"],
                                          "prop": "wikitext", "section": section["index"],
                                          "format": "json"})["parse"]["wikitext"]["*"]
        return {"page": parsed["title"], "revid": parsed["revid"], "heading": section["line"],
                "index": section["index"], "wikitext": text}

    def resolve_enwiki_titles(self, titles):
        """Map each requested enwiki title to its page, Wikidata QID and status flags."""
        result = {}
        for batch in _chunks(list(titles), BATCH_SIZE):
            query = self.get_json(ENWIKI_API, {
                "action": "query", "format": "json", "redirects": 1,
                "prop": "pageprops", "ppprop": "wikibase_item|disambiguation",
                "titles": "|".join(batch),
            })["query"]
            renames = {r["from"]: r["to"]
                       for key in ("normalized", "redirects")
                       for r in query.get(key, [])}
            pages = {p["title"]: p for p in query["pages"].values()}
            for requested in batch:
                title = requested
                while title in renames:
                    title = renames[title]
                page = pages.get(title, {"missing": ""})
                props = page.get("pageprops", {})
                result[requested] = {
                    "resolved_title": title,
                    "qid": props.get("wikibase_item"),
                    "is_disambiguation": "disambiguation" in props,
                    "missing": "missing" in page,
                }
        return result

    def get_entities(self, ids, props="labels|descriptions|claims|sitelinks"):
        """Fetch Wikidata entities (items or properties) by ID, batched."""
        entities = {}
        for batch in _chunks(list(ids), BATCH_SIZE):
            entities.update(self.get_json(WIKIDATA_API, {
                "action": "wbgetentities", "format": "json", "ids": "|".join(batch),
                "props": props, "languages": "en|mul", "sitefilter": "enwiki",
            })["entities"])
        return entities
