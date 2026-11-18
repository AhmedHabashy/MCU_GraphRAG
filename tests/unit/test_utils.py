"""Unit tests for src/utils.py. No network: a fake HTTP session is injected."""

import pytest
import requests

from src.utils import (
    FandomClient,
    JsonHttpClient,
    WikimediaClient,
    claim_values,
    claims_with_qualifiers,
    day_dates,
    quantities,
    earliest_year,
    label,
    qualifier_value,
)


# --- fake HTTP layer (dependency injected into WikimediaClient) -------------

class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Returns queued responses in order and records every call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return self.responses.pop(0)


def make_client(responses):
    session = FakeSession(responses)
    return WikimediaClient(session=session, sleep=lambda _s: None), session


# --- entity fixtures --------------------------------------------------------

def item_snak(qid):
    return {"mainsnak": {"datavalue": {"type": "wikibase-entityid",
                                       "value": {"id": qid}}}}


def string_snak(value):
    return {"mainsnak": {"datavalue": {"type": "string", "value": value}}}


def time_snak(time):
    return {"mainsnak": {"datavalue": {"type": "time", "value": {"time": time}}}}


def novalue_snak():
    return {"mainsnak": {"snaktype": "novalue"}}


# --- claim_values -----------------------------------------------------------

def test_claim_values_returns_item_ids():
    entity = {"claims": {"P31": [item_snak("Q11424"), item_snak("Q1259759")]}}
    assert claim_values(entity, "P31") == ["Q11424", "Q1259759"]


def test_claim_values_returns_plain_strings_for_external_ids():
    entity = {"claims": {"P345": [string_snak("tt0371746")]}}
    assert claim_values(entity, "P345") == ["tt0371746"]


def test_claim_values_skips_snaks_without_a_value():
    entity = {"claims": {"P345": [novalue_snak(), string_snak("tt1")]}}
    assert claim_values(entity, "P345") == ["tt1"]


def test_claim_values_is_empty_for_missing_property():
    assert claim_values({"claims": {}}, "P4947") == []


def with_rank(claim, rank):
    return {**claim, "rank": rank}


def test_claim_values_ignores_deprecated_claims():
    entity = {"claims": {"P577": [
        with_rank(time_snak("+2021-11-05T00:00:00Z"), "deprecated"),
        with_rank(time_snak("+2022-05-06T00:00:00Z"), "normal"),
    ]}}
    assert claim_values(entity, "P577") == [{"time": "+2022-05-06T00:00:00Z"}]


def test_claim_values_returns_only_preferred_when_present():
    entity = {"claims": {"P345": [
        with_rank(string_snak("tt_old"), "normal"),
        with_rank(string_snak("tt_best"), "preferred"),
    ]}}
    assert claim_values(entity, "P345") == ["tt_best"]


# --- qualifier_value --------------------------------------------------------

def test_qualifier_value_reads_first_best_rank_claim_qualifier():
    claim = {**item_snak("Q64349029"),
             "qualifiers": {"P1545": [{"datavalue": {"type": "string", "value": "2"}}]}}
    entity = {"claims": {"P179": [claim]}}
    assert qualifier_value(entity, "P179", "P1545") == ("Q64349029", "2")


def test_qualifier_value_is_none_without_the_qualifier():
    entity = {"claims": {"P179": [item_snak("Q64349029")]}}
    assert qualifier_value(entity, "P179", "P1545") == ("Q64349029", None)


def test_qualifier_value_is_none_without_the_claim():
    assert qualifier_value({"claims": {}}, "P179", "P1545") == (None, None)


def qualified(qid, *roles):
    return {**item_snak(qid), "qualifiers": {"P453": [
        {"datavalue": {"type": "wikibase-entityid", "value": {"id": r}}} for r in roles]}}


def test_claims_with_qualifiers_lists_every_claim_and_qualifier():
    entity = {"claims": {"P161": [qualified("Q1", "Q10", "Q11"), item_snak("Q2")]}}
    assert claims_with_qualifiers(entity, "P161", "P453") == [
        ("Q1", ["Q10", "Q11"]), ("Q2", [])]


# --- FandomClient -----------------------------------------------------------

def test_fandom_lead_returns_first_section_with_revision():
    payload = {"parse": {"title": "Anthony Stark (Earth-199999)", "revid": 11251179,
                         "wikitext": {"*": "{{Marvel Database:Character Template}}"}}}
    session = FakeSession([FakeResponse(200, payload=payload)])
    client = FandomClient(session=session, sleep=lambda _s: None)

    lead = client.lead("marvel", "Anthony_Stark_(Earth-199999)")

    assert lead == {"page": "Anthony Stark (Earth-199999)", "revid": 11251179,
                    "wikitext": "{{Marvel Database:Character Template}}",
                    "url": "https://marvel.fandom.com/wiki/Anthony_Stark_(Earth-199999)"}
    url, params = session.calls[0]
    assert url == "https://marvel.fandom.com/api.php"
    assert params["page"] == "Anthony Stark (Earth-199999)" and params["section"] == 0


def test_fandom_search_returns_page_titles():
    payload = {"query": {"search": [{"title": "Katy Chen"}, {"title": "Katy (disambiguation)"}]}}
    session = FakeSession([FakeResponse(200, payload=payload)])
    client = FandomClient(session=session, sleep=lambda _s: None)

    assert client.search("marvelcinematicuniverse", "Katy", limit=2) == ["Katy Chen", "Katy (disambiguation)"]
    url, params = session.calls[0]
    assert url == "https://marvelcinematicuniverse.fandom.com/api.php"
    assert params["srsearch"] == "Katy" and params["srlimit"] == 2


def test_fandom_search_retries_temporary_api_errors():
    """MediaWiki reports some failures as HTTP 200 with an 'error' object."""
    session = FakeSession([FakeResponse(200, payload={"error": {"code": "search-backend-error"}}),
                           FakeResponse(200, payload={"query": {"search": [{"title": "Katy Chen"}]}})])
    client = FandomClient(session=session, sleep=lambda _s: None)
    assert client.search("marvelcinematicuniverse", "Katy", limit=1) == ["Katy Chen"]
    assert len(session.calls) == 2


def test_fandom_search_fails_clearly_on_other_api_errors():
    session = FakeSession([FakeResponse(200, payload={"error": {"code": "badvalue"}})])
    client = FandomClient(session=session, sleep=lambda _s: None)
    with pytest.raises(RuntimeError, match="badvalue"):
        client.search("marvelcinematicuniverse", "Katy", limit=1)


def test_fandom_lead_is_none_for_missing_pages():
    session = FakeSession([FakeResponse(200, payload={"error": {"code": "missingtitle"}})])
    assert FandomClient(session=session, sleep=lambda _s: None).lead("marvel", "Nope") is None


# --- day_dates ----------------------------------------------------------------

def dated(time, precision, rank="normal"):
    return {"mainsnak": {"datavalue": {"type": "time",
                                       "value": {"time": time, "precision": precision}}},
            "rank": rank}


def test_day_dates_include_every_non_deprecated_day_precision_date():
    """Premieres are usually normal rank next to a preferred national release date."""
    entity = {"claims": {"P577": [dated("+2008-05-02T00:00:00Z", 11, "preferred"),
                                  dated("+2008-04-14T00:00:00Z", 11),
                                  dated("+2007-01-01T00:00:00Z", 11, "deprecated"),
                                  dated("+2008-00-00T00:00:00Z", 9)]}}       # year only
    assert day_dates(entity, "P577") == ["2008-04-14", "2008-05-02"]


def test_day_dates_is_empty_without_claims():
    assert day_dates({"claims": {}}, "P577") == []


# --- quantities ---------------------------------------------------------------

def amount(value, unit, rank="normal"):
    return {"mainsnak": {"datavalue": {"type": "quantity", "value": {
        "amount": value, "unit": f"http://www.wikidata.org/entity/{unit}"}}}, "rank": rank}


def test_quantities_return_every_non_deprecated_amount_with_its_unit():
    entity = {"claims": {"P2142": [amount("+2799439100", "Q4917"), amount("+858373000", "Q4917", "preferred"),
                                   amount("+1", "Q4917", "deprecated"), amount("+100", "Q4916")]}}
    assert quantities(entity, "P2142") == [(2799439100.0, "Q4917"), (858373000.0, "Q4917"), (100.0, "Q4916")]


def test_quantities_without_a_unit_use_one():
    entity = {"claims": {"P2047": [{"mainsnak": {"datavalue": {"type": "quantity", "value": {
        "amount": "+126", "unit": "1"}}}, "rank": "normal"}]}}
    assert quantities(entity, "P2047") == [(126.0, "1")]


# --- label ------------------------------------------------------------------

def test_label_prefers_english():
    entity = {"labels": {"en": {"value": "Thor"}, "mul": {"value": "Thor M"}}}
    assert label(entity) == "Thor"


def test_label_falls_back_to_multilingual_default():
    assert label({"labels": {"mul": {"value": "X2"}}}) == "X2"


def test_label_is_none_when_absent():
    assert label({"labels": {}}) is None


# --- earliest_year ----------------------------------------------------------

def test_earliest_year_uses_minimum_publication_date():
    entity = {"claims": {"P577": [time_snak("+2008-05-02T00:00:00Z"),
                                  time_snak("+2008-04-14T00:00:00Z"),
                                  time_snak("+2009-01-01T00:00:00Z")]}}
    assert earliest_year(entity) == 2008


def test_earliest_year_falls_back_to_start_time():
    entity = {"claims": {"P580": [time_snak("+2021-08-11T00:00:00Z")]}}
    assert earliest_year(entity) == 2021


def test_earliest_year_is_none_without_dates():
    assert earliest_year({"claims": {}}) is None


# --- WikimediaClient: retries -----------------------------------------------

def test_client_retries_after_rate_limit_then_returns_json():
    client, session = make_client([
        FakeResponse(429, headers={"Retry-After": "1"}),
        FakeResponse(200, payload={"ok": True}),
    ])
    assert client.get_json("https://example.org/api", {"a": 1}) == {"ok": True}
    assert len(session.calls) == 2


def test_client_gives_up_after_max_retries():
    client, _ = make_client([FakeResponse(503)] * 10)
    with pytest.raises(RuntimeError):
        client.get_json("https://example.org/api", {})


class FlakySession(FakeSession):
    """Raises the given exceptions first, then returns the queued responses."""

    def __init__(self, errors, responses):
        super().__init__(responses)
        self.errors = list(errors)

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        if self.errors:
            raise self.errors.pop(0)
        return self.responses.pop(0)


def test_client_retries_timeouts_and_connection_errors():
    session = FlakySession([requests.exceptions.ReadTimeout("slow"),
                            requests.exceptions.ConnectionError("dropped")],
                           [FakeResponse(200, payload={"ok": True})])
    client = JsonHttpClient(session=session, sleep=lambda _s: None)
    assert client.get_json("https://example.org/api", {}) == {"ok": True}
    assert len(session.calls) == 3


def test_client_gives_up_on_repeated_timeouts_without_leaking_parameters():
    leak = "https://api.example.org/3/movie/1?api_key=SECRET"
    session = FlakySession([requests.exceptions.ConnectionError(f"Max retries with url: {leak}")] * 10, [])
    client = JsonHttpClient(session=session, sleep=lambda _s: None)
    with pytest.raises(RuntimeError) as error:
        client.get_json("https://api.example.org/3/movie/1", {"api_key": "SECRET"})
    assert "SECRET" not in str(error.value) and error.value.__cause__ is None
    assert "ConnectionError" in str(error.value)


def test_sparql_allows_the_query_services_full_minute():
    session = FlakySession([], [FakeResponse(200, payload={"results": {"bindings": []}})])
    WikimediaClient(session=session, sleep=lambda _s: None).sparql("SELECT ...")
    assert session.calls[0][2] == 60


def test_client_errors_never_include_request_parameters():
    """Parameters can hold secrets (TMDB api_key), so errors name only the URL."""
    client = JsonHttpClient(session=FakeSession([FakeResponse(401)]), sleep=lambda _s: None)
    with pytest.raises(RuntimeError) as error:
        client.get_json("https://api.example.org/3/movie/1", {"api_key": "SECRET"})
    assert "SECRET" not in str(error.value)
    assert "401" in str(error.value)


# --- WikimediaClient: sparql ------------------------------------------------

def test_sparql_returns_bindings_as_plain_values():
    payload = {"results": {"bindings": [
        {"actor": {"type": "uri", "value": "http://www.wikidata.org/entity/Q165219"},
         "tmdb": {"type": "literal", "value": "3223"}}]}}
    client, session = make_client([FakeResponse(200, payload=payload)])

    rows = client.sparql("SELECT ...")

    assert rows == [{"actor": "Q165219", "tmdb": "3223"}]
    assert session.calls[0][0] == "https://query.wikidata.org/sparql"


# --- WikimediaClient: top_level_section -------------------------------------

def test_top_level_section_returns_wikitext_of_first_matching_heading():
    sections = {"parse": {"title": "Loki season 2", "revid": 1376841848, "sections": [
        {"index": "1", "line": "Episodes", "toclevel": 1},
        {"index": "6", "line": "Casting", "toclevel": 2},
        {"index": "2", "line": "Cast and characters", "toclevel": 1}]}}
    wikitext = {"parse": {"title": "Loki season 2", "wikitext": {"*": "* [[Tom Hiddleston]] as Loki"}}}
    client, session = make_client([FakeResponse(200, payload=sections),
                                   FakeResponse(200, payload=wikitext)])

    section = client.top_level_section("Loki season 2", prefix="Cast")

    assert section == {"page": "Loki season 2", "revid": 1376841848,
                       "heading": "Cast and characters",
                       "index": "2", "wikitext": "* [[Tom Hiddleston]] as Loki"}
    assert session.calls[1][1]["section"] == "2"
    assert session.calls[1][1]["oldid"] == 1376841848  # text from the same revision


def test_top_level_section_prefers_earlier_prefixes_over_page_order():
    sections = {"parse": {"title": "F", "revid": 7, "sections": [
        {"index": "1", "line": "Premise", "toclevel": 1},
        {"index": "2", "line": "Plot", "toclevel": 1}]}}
    wikitext = {"parse": {"title": "F", "wikitext": {"*": "== Plot =="}}}
    client, _ = make_client([FakeResponse(200, payload=sections),
                             FakeResponse(200, payload=wikitext)])

    assert client.top_level_section("F", prefix=("Plot", "Premise"))["heading"] == "Plot"


def test_top_level_section_is_none_when_heading_absent():
    sections = {"parse": {"title": "X", "revid": 1, "sections": [
        {"index": "1", "line": "Plot", "toclevel": 1}]}}
    client, _ = make_client([FakeResponse(200, payload=sections)])
    assert client.top_level_section("X", prefix="Cast") is None


# --- WikimediaClient: resolve_enwiki_titles ---------------------------------

def test_resolve_enwiki_titles_follows_redirects_and_flags_disambiguation():
    payload = {"query": {
        "redirects": [{"from": "Thor (film)", "to": "Thor (2011 film)"}],
        "pages": {
            "1": {"title": "Thor (2011 film)",
                  "pageprops": {"wikibase_item": "Q217020"}},
            "2": {"title": "X-Men",
                  "pageprops": {"wikibase_item": "Q128452",
                                "disambiguation": ""}},
            "-1": {"title": "No Such Page", "missing": ""},
        },
    }}
    client, session = make_client([FakeResponse(200, payload=payload)])

    result = client.resolve_enwiki_titles(["Thor (film)", "X-Men", "No Such Page"])

    assert result["Thor (film)"] == {"resolved_title": "Thor (2011 film)",
                                     "qid": "Q217020",
                                     "is_disambiguation": False,
                                     "missing": False}
    assert result["X-Men"]["is_disambiguation"] is True
    assert result["No Such Page"]["missing"] is True
    assert result["No Such Page"]["qid"] is None
    assert session.calls[0][0] == "https://en.wikipedia.org/w/api.php"


def test_resolve_enwiki_titles_applies_title_normalization():
    payload = {"query": {
        "normalized": [{"from": "x2 (film)", "to": "X2 (film)"}],
        "pages": {"1": {"title": "X2 (film)",
                        "pageprops": {"wikibase_item": "Q219776"}}},
    }}
    client, _ = make_client([FakeResponse(200, payload=payload)])
    assert client.resolve_enwiki_titles(["x2 (film)"])["x2 (film)"]["qid"] == "Q219776"


# --- WikimediaClient: get_entities ------------------------------------------

def test_get_entities_batches_requests_of_fifty():
    qids = [f"Q{i}" for i in range(1, 76)]
    first = {"entities": {q: {"id": q} for q in qids[:50]}}
    second = {"entities": {q: {"id": q} for q in qids[50:]}}
    client, session = make_client([FakeResponse(200, payload=first),
                                   FakeResponse(200, payload=second)])

    entities = client.get_entities(qids)

    assert set(entities) == set(qids)
    assert len(session.calls) == 2
    assert session.calls[0][1]["ids"].count("|") == 49
    assert session.calls[0][0] == "https://www.wikidata.org/w/api.php"
    assert "mul" in session.calls[0][1]["languages"].split("|")
