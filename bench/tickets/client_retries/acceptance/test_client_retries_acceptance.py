"""Hidden acceptance tests for the client_retries ticket. Identical for every arm. Never shown to the agent."""
import asyncio
import os

import pytest

import httpx

NO_WAIT = dict(backoff_factor=0)


def _transport(script, calls):
    """script: dict path -> list of int | (int, headers) | Exception, consumed in order."""
    queues = {k: list(v) for k, v in script.items()}

    def handler(request):
        calls.append((request.method, request.url.path))
        item = queues[request.url.path].pop(0)
        if isinstance(item, Exception):
            raise item
        status, headers = (item, {}) if isinstance(item, int) else item
        return httpx.Response(status, headers=headers)

    return httpx.MockTransport(handler)


def test_exports():
    assert "Retry" in httpx.__all__ and "RetryError" in httpx.__all__
    assert issubclass(httpx.RetryError, httpx.RequestError)


def test_retry_defaults_and_equality():
    r = httpx.Retry()
    assert r.total == 3 and r.backoff_factor == 0.5
    assert tuple(r.status_forcelist) == (429, 500, 502, 503, 504)
    assert "GET" in r.allowed_methods and "POST" not in r.allowed_methods
    assert httpx.Retry(2, backoff_factor=0) == httpx.Retry(2, backoff_factor=0)
    assert httpx.Retry(2) != httpx.Retry(3)
    assert "Retry" in repr(r)


def test_backoff_for():
    r = httpx.Retry(backoff_factor=0.5)
    assert [r.backoff_for(n) for n in (1, 2, 3)] == [0.5, 1.0, 2.0]
    resp = httpx.Response(503, headers={"Retry-After": "4"})
    assert r.backoff_for(1, resp) == 4
    assert httpx.Retry(respect_retry_after=False).backoff_for(1, resp) == 0.5


def test_client_retries_property():
    assert httpx.Client().retries == httpx.Retry(0)
    c = httpx.Client(retries=3)
    assert isinstance(c.retries, httpx.Retry) and c.retries.total == 3
    c.retries = httpx.Retry(1, **NO_WAIT)
    assert c.retries == httpx.Retry(1, **NO_WAIT)


def test_default_client_does_not_retry():
    calls = []
    c = httpx.Client(transport=_transport({"/": [503, 200]}, calls))
    r = c.get("https://example.org/")
    assert r.status_code == 503 and len(calls) == 1
    assert r.extensions["retries"] == 0


def test_status_retry_then_success():
    calls = []
    c = httpx.Client(transport=_transport({"/": [503, 502, 200]}, calls), retries=httpx.Retry(3, **NO_WAIT))
    r = c.get("https://example.org/")
    assert r.status_code == 200 and len(calls) == 3
    assert r.extensions["retries"] == 2


def test_int_shorthand():
    calls = []
    c = httpx.Client(transport=_transport({"/": [500, 200]}, calls), retries=1)
    assert c.get("https://example.org/").status_code == 200 and len(calls) == 2


def test_exhausted_status_returns_last_response():
    calls = []
    c = httpx.Client(transport=_transport({"/": [500, 500, 500, 200]}, calls), retries=httpx.Retry(2, **NO_WAIT))
    r = c.get("https://example.org/")
    assert r.status_code == 500 and len(calls) == 3 and r.extensions["retries"] == 2


def test_post_not_retried():
    calls = []
    c = httpx.Client(transport=_transport({"/": [503, 200]}, calls), retries=httpx.Retry(3, **NO_WAIT))
    assert c.post("https://example.org/", content=b"x").status_code == 503
    assert calls == [("POST", "/")]


def test_transport_error_exhausted_raises_retry_error():
    calls = []
    errs = [httpx.ConnectError("boom")] * 3
    c = httpx.Client(transport=_transport({"/": errs}, calls), retries=httpx.Retry(2, **NO_WAIT))
    with pytest.raises(httpx.RetryError) as ei:
        c.get("https://example.org/")
    assert isinstance(ei.value.last_exception, httpx.ConnectError)
    assert ei.value.__cause__ is ei.value.last_exception
    assert ei.value.attempts == 3 and len(calls) == 3


def test_transport_error_then_success():
    calls = []
    c = httpx.Client(transport=_transport({"/": [httpx.ReadTimeout("t"), 200]}, calls), retries=httpx.Retry(1, **NO_WAIT))
    assert c.get("https://example.org/").status_code == 200


def test_per_request_override_disables():
    calls = []
    c = httpx.Client(transport=_transport({"/": [503, 200]}, calls), retries=httpx.Retry(3, **NO_WAIT))
    assert c.get("https://example.org/", extensions={"retries": 0}).status_code == 503 and len(calls) == 1


def test_per_request_override_enables():
    calls = []
    c = httpx.Client(transport=_transport({"/": [503, 200]}, calls))
    r = c.get("https://example.org/", extensions={"retries": httpx.Retry(1, **NO_WAIT)})
    assert r.status_code == 200 and len(calls) == 2


def test_redirect_hops_retried_independently():
    calls = []
    script = {"/a": [(302, {"Location": "/b"})], "/b": [503, 200]}
    c = httpx.Client(transport=_transport(script, calls), retries=httpx.Retry(2, **NO_WAIT), follow_redirects=True)
    r = c.get("https://example.org/a")
    assert r.status_code == 200
    assert calls == [("GET", "/a"), ("GET", "/b"), ("GET", "/b")]
    assert len(r.history) == 1


def test_response_hook_sees_only_final_attempt():
    seen = []
    calls = []
    c = httpx.Client(
        transport=_transport({"/": [503, 503, 200]}, calls),
        retries=httpx.Retry(3, **NO_WAIT),
        event_hooks={"response": [lambda r: seen.append(r.status_code)]},
    )
    c.get("https://example.org/")
    assert seen == [200]


def test_async_client_retries():
    calls = []

    async def main():
        async with httpx.AsyncClient(
            transport=_transport({"/": [502, httpx.ConnectError("x"), 200]}, calls),
            retries=httpx.Retry(3, **NO_WAIT),
        ) as c:
            return await c.get("https://example.org/")

    r = asyncio.run(main())
    assert r.status_code == 200 and len(calls) == 3 and r.extensions["retries"] == 2


def test_async_exhausted_raises():
    async def main():
        async with httpx.AsyncClient(
            transport=_transport({"/": [httpx.ConnectError("x")] * 2}, []),
            retries=httpx.Retry(1, **NO_WAIT),
        ) as c:
            await c.get("https://example.org/")

    with pytest.raises(httpx.RetryError):
        asyncio.run(main())


def test_docs_page_linked():
    root = os.path.dirname(os.path.dirname(httpx.__file__))
    assert os.path.exists(os.path.join(root, "docs", "advanced", "retries.md"))
    assert "advanced/retries.md" in open(os.path.join(root, "mkdocs.yml"), encoding="utf-8").read()
