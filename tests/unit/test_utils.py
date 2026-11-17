"""Unit tests for src/utils.py. No network: a fake HTTP session is injected."""

import pytest

from src.utils import (
    WikimediaClient,
    claim_values,
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
