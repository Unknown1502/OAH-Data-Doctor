"""The FHIR client is read-only, stays on its host, pages correctly and retries politely."""

import asyncio
import json

import httpx
import pytest

from datadoctor.ingestion.fhir_client import FhirClient, ReadOnlyViolation, SandboxUnavailable

BASE = "https://sandbox.example.org/fhir"


def _bundle(ids, next_url=None):
    b = {"resourceType": "Bundle", "type": "searchset",
         "entry": [{"resource": {"resourceType": "Observation", "id": i}} for i in ids], "link": []}
    if next_url:
        b["link"].append({"relation": "next", "url": next_url})
    return b


def _client(handler):
    return FhirClient(BASE, None, delay_s=0, retries=2, transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "POST"])
def test_write_methods_are_refused(method):
    with pytest.raises(ReadOnlyViolation):
        FhirClient.check_method(method, f"{BASE}/Observation/x")


def test_validate_is_the_only_allowed_post():
    FhirClient.check_method("POST", f"{BASE}/Observation/$validate")
    FhirClient.check_method("GET", f"{BASE}/Observation")


def test_paging_follows_next_links_and_filters_client_side():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if "_getpages" in str(req.url):
            b = _bundle(["c"])
            b["entry"].append({"resource": {"resourceType": "Library", "id": "not-an-observation"}})
            return httpx.Response(200, json=b)
        return httpx.Response(200, json=_bundle(["a", "b"], f"{BASE}?_getpages=x&_getpagesoffset=2"))

    async def go():
        async with _client(handler) as c:
            return await c.search_all("Observation", 2)

    res = asyncio.run(go())
    assert [r["id"] for r in res] == ["a", "b", "c"]
    assert len(calls) == 2


def test_next_link_to_another_host_is_refused():
    def handler(req):
        return httpx.Response(200, json=_bundle(["a"], "https://evil.example.com/fhir?_getpages=1"))

    async def go():
        async with _client(handler) as c:
            await c.search_all("Observation")

    with pytest.raises(ReadOnlyViolation):
        asyncio.run(go())


def test_retries_on_503_then_succeeds():
    n = {"i": 0}

    def handler(req):
        n["i"] += 1
        if n["i"] == 1:
            return httpx.Response(503, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"resourceType": "CapabilityStatement", "fhirVersion": "4.0.1"})

    async def go():
        async with _client(handler) as c:
            return await c.capability_statement()

    assert asyncio.run(go())["fhirVersion"] == "4.0.1"
    assert n["i"] == 2


def test_gives_up_after_retries():
    def handler(req):
        return httpx.Response(500, headers={"Retry-After": "0"})

    async def go():
        async with _client(handler) as c:
            await c.capability_statement()

    with pytest.raises(SandboxUnavailable):
        asyncio.run(go())


def test_raw_body_is_returned_verbatim():
    body = json.dumps({"resourceType": "Observation", "id": "x", "valueQuantity": {"value": 19.80}})

    def handler(req):
        return httpx.Response(200, content=body.encode(), headers={"Content-Type": "application/fhir+json"})

    async def go():
        async with _client(handler) as c:
            return await c.request("GET", "Observation/x")

    assert asyncio.run(go())[1] == body
