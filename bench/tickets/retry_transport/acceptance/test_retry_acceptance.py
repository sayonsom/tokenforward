"""Hidden acceptance tests. Identical for every arm. Never shown to the agent."""
import asyncio

import pytest

import httpx


def _seq(statuses, record=None):
    it = iter(statuses)

    def handler(request):
        if record is not None:
            record.append(request.method)
        s = next(it)
        if isinstance(s, Exception):
            raise s
        headers = {}
        if isinstance(s, tuple):
            s, headers = s
        return httpx.Response(s, headers=headers)

    return handler


def _client(statuses, record=None, **kw):
    sleeps = []
    t = httpx.RetryTransport(
        httpx.MockTransport(_seq(statuses, record)), sleep=sleeps.append, **kw
    )
    return httpx.Client(transport=t), sleeps


def test_exported():
    assert "RetryTransport" in httpx.__all__
    assert "AsyncRetryTransport" in httpx.__all__


def test_retries_then_succeeds_with_backoff():
    calls = []
    c, sleeps = _client([503, 503, 200], calls)
    r = c.get("https://example.org/")
    assert r.status_code == 200
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]


def test_non_idempotent_not_retried():
    calls = []
    c, sleeps = _client([503, 200], calls)
    r = c.post("https://example.org/", content=b"x")
    assert r.status_code == 503
    assert calls == ["POST"]
    assert sleeps == []


def test_exhausted_returns_last_response():
    calls = []
    c, _ = _client([500, 500, 500, 200], calls, max_retries=2)
    r = c.get("https://example.org/")
    assert r.status_code == 500
    assert len(calls) == 3


def test_transport_error_retried():
    calls = []
    c, _ = _client([httpx.ConnectError("x"), httpx.ReadTimeout("y"), 200], calls)
    assert c.get("https://example.org/").status_code == 200
    assert len(calls) == 3


def test_transport_error_exhausted_reraises():
    c, _ = _client([httpx.ConnectError("a")] * 3, max_retries=2)
    with pytest.raises(httpx.ConnectError):
        c.get("https://example.org/")


def test_retry_after_header_wins():
    c, sleeps = _client([(429, {"Retry-After": "7"}), 200])
    assert c.get("https://example.org/").status_code == 200
    assert sleeps == [7]


def test_status_not_in_list_passes_through():
    calls = []
    c, _ = _client([404, 200], calls)
    assert c.get("https://example.org/").status_code == 404
    assert len(calls) == 1


def test_async_retries():
    sleeps = []

    async def fake_sleep(d):
        sleeps.append(d)

    async def main():
        t = httpx.AsyncRetryTransport(
            httpx.MockTransport(_seq([502, 200])), sleep=fake_sleep
        )
        async with httpx.AsyncClient(transport=t) as c:
            return await c.get("https://example.org/")

    r = asyncio.run(main())
    assert r.status_code == 200
    assert sleeps == [0.5]
