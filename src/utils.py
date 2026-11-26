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
DEFAULT_TIMEOUT = 30   # seconds
SPARQL_TIMEOUT = 60    # the Wikidata query service's own query time limit
# MediaWiki API error codes (in an HTTP 200 body) that are worth retrying
TEMPORARY_API_ERRORS = ("search-backend-error", "internal_api_error", "ratelimited", "maxlag")

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


DAY_PRECISION = 11


def day_dates(entity, pid):
    """Sorted 'YYYY-MM-DD' dates of every non-deprecated, day-precision `pid` claim.

    Unlike claim_values (best rank only), this keeps normal-rank dates too, so a film's
    premiere is found next to a preferred national release date.
    """
    dates = set()
    for claim in entity.get("claims", {}).get(pid, []):
        value = (claim["mainsnak"].get("datavalue") or {}).get("value")
        if claim.get("rank") != "deprecated" and value and value.get("precision") == DAY_PRECISION:
            dates.add(value["time"][1:11])
    return sorted(dates)


def quantities(entity, pid):
    """(amount, unit QID or '1') of every non-deprecated quantity claim, in claim order.
    Box office has one normal-rank claim per region, so every rank but deprecated is kept."""
    found = []
    for claim in entity.get("claims", {}).get(pid, []):
        value = (claim["mainsnak"].get("datavalue") or {}).get("value")
        if claim.get("rank") != "deprecated" and value and "amount" in value:
            found.append((float(value["amount"]), value["unit"].removeprefix(ENTITY_URI_PREFIX)))
    return found


def claims_with_qualifier_map(entity, pid, qualifier_pids):
    """[(value, {qualifier pid: [values]})] for every best-rank `pid` claim that has a value."""
    pairs = []
    for claim in _best_claims(entity, pid):
        value = _snak_value(claim["mainsnak"])
        if value is None:
            continue
        qualifiers = claim.get("qualifiers", {})
        pairs.append((value, {q: [v for v in map(_snak_value, qualifiers.get(q, [])) if v is not None]
                              for q in qualifier_pids}))
    return pairs


def claims_with_qualifiers(entity, pid, qualifier_pid):
    """[(value, [qualifier values])] for every best-rank `pid` claim that has a value."""
    return [(value, by_pid[qualifier_pid])
            for value, by_pid in claims_with_qualifier_map(entity, pid, (qualifier_pid,))]


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
    """GET or POST JSON with retry on rate limiting / server errors (honours Retry-After).

    `session` and `sleep` are injected so tests can run without the network.
    Error messages name only the URL, never the parameters, which may hold secrets.
    """

    def __init__(self, session=None, sleep=time.sleep):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.sleep = sleep

    def get_json(self, url, params, timeout=DEFAULT_TIMEOUT):
        return self._json(url, lambda: self.session.get(url, params=params, timeout=timeout))

    def post_json(self, url, body, timeout=DEFAULT_TIMEOUT):
        """POST a JSON body; errors name only the URL, like get_json."""
        return self._json(url, lambda: self.session.post(url, json=body, timeout=timeout))

    def _json(self, url, send):
        """Retries rate limits, server errors, timeouts and dropped connections. Network errors
        are re-raised without their message, which can contain the full URL with parameters."""
        last = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = send()
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as error:
                last, wait = type(error).__name__, 2 ** attempt
            else:
                if response.status_code < 400:
                    return response.json()
                if response.status_code not in RETRYABLE_STATUS:
                    raise RuntimeError(f"{url} returned HTTP {response.status_code}")
                last = f"status {response.status_code}"
                wait = float(response.headers.get("Retry-After", 2 ** attempt))
            if attempt < MAX_ATTEMPTS:
                self.sleep(wait)
        raise RuntimeError(f"{url} still failing after {MAX_ATTEMPTS} attempts (last: {last})")


class FandomClient(JsonHttpClient):
    """Client for Fandom wikis (MediaWiki API at https://<wiki>.fandom.com/api.php)."""

    def search(self, wiki, query, limit):
        """Titles of the top full-text search hits. MediaWiki reports some temporary failures
        as HTTP 200 with an 'error' object; those are retried, others raise."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            found = self.get_json(f"https://{wiki}.fandom.com/api.php", {
                "action": "query", "list": "search", "srsearch": query, "srlimit": limit,
                "format": "json"})
            if "query" in found:
                return [hit["title"] for hit in found["query"]["search"]]
            code = found.get("error", {}).get("code", "no 'query' in response")
            if not code.startswith(TEMPORARY_API_ERRORS) or attempt == MAX_ATTEMPTS:
                break
            self.sleep(2 ** attempt)
        raise RuntimeError(f"{wiki} search failed: {code}")

    def page(self, wiki, page):
        """Whole-page wikitext with its revision, or None if missing."""
        parsed = self.get_json(f"https://{wiki}.fandom.com/api.php", {
            "action": "parse", "page": page, "prop": "wikitext|revid", "redirects": 1, "format": "json"})
        if "error" in parsed:
            return None
        title = parsed["parse"]["title"]
        return {"page": title, "revid": parsed["parse"]["revid"],
                "wikitext": parsed["parse"]["wikitext"]["*"], "url": fandom_url(wiki, title)}

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
        bindings = self.get_json(WIKIDATA_SPARQL, {"format": "json", "query": query},
                                 timeout=SPARQL_TIMEOUT)
        return [{name: cell["value"].removeprefix(ENTITY_URI_PREFIX)
                 for name, cell in row.items()}
                for row in bindings["results"]["bindings"]]

    def article(self, page):
        """Whole enwiki article: {'page', 'revid', 'wikitext', 'url'} (redirects followed)."""
        parsed = self.get_json(ENWIKI_API, {"action": "parse", "page": page, "prop": "wikitext|revid",
                                            "redirects": 1, "format": "json"})["parse"]
        return {"page": parsed["title"], "revid": parsed["revid"], "wikitext": parsed["wikitext"]["*"],
                "url": enwiki_url(parsed["title"])}

    def sections(self, page):
        """{'title', 'revid', 'sections'}: the section list of an enwiki page (redirects followed)."""
        return self.get_json(ENWIKI_API, {"action": "parse", "page": page, "prop": "sections|revid",
                                          "redirects": 1, "format": "json"})["parse"]

    def top_level_section(self, page, prefix):
        """Top-level section of `page` whose heading starts with `prefix`, or None.

        `prefix` may be a tuple; earlier prefixes win over page order. The wikitext
        is read from the same revision as the section list, and its revid returned.
        """
        parsed = self.sections(page)
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
