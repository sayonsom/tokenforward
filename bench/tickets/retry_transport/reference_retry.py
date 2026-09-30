# Instructor-only reference solution. Validates the acceptance tests. Not given to any arm.
from __future__ import annotations

import asyncio
import time
import typing

from .._exceptions import TransportError
from .._models import Request, Response
from .base import AsyncBaseTransport, BaseTransport

__all__ = ["AsyncRetryTransport", "RetryTransport"]

IDEMPOTENT = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE", "TRACE"})


class _Policy:
    def __init__(self, max_retries, backoff_factor, retry_on_status):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.retry_on_status = frozenset(retry_on_status)

    def delay(self, attempt: int, response: Response | None) -> float:
        if response is not None:
            ra = response.headers.get("Retry-After", "")
            if ra.isdigit():
                return int(ra)
        return self.backoff_factor * 2 ** (attempt - 1)


class RetryTransport(BaseTransport):
    def __init__(self, transport: BaseTransport, *, max_retries: int = 3,
                 backoff_factor: float = 0.5,
                 retry_on_status: typing.Iterable[int] = (429, 500, 502, 503, 504),
                 sleep: typing.Callable[[float], None] = time.sleep) -> None:
        self._transport = transport
        self._policy = _Policy(max_retries, backoff_factor, retry_on_status)
        self._sleep = sleep

    def handle_request(self, request: Request) -> Response:
        p = self._policy
        if request.method not in IDEMPOTENT:
            return self._transport.handle_request(request)
        for attempt in range(1, p.max_retries + 2):
            last = attempt > p.max_retries
            try:
                response = self._transport.handle_request(request)
            except TransportError:
                if last:
                    raise
                self._sleep(p.delay(attempt, None))
                continue
            if last or response.status_code not in p.retry_on_status:
                return response
            response.close()
            self._sleep(p.delay(attempt, response))
        raise AssertionError("unreachable")  # pragma: no cover

    def close(self) -> None:
        self._transport.close()


class AsyncRetryTransport(AsyncBaseTransport):
    def __init__(self, transport: AsyncBaseTransport, *, max_retries: int = 3,
                 backoff_factor: float = 0.5,
                 retry_on_status: typing.Iterable[int] = (429, 500, 502, 503, 504),
                 sleep: typing.Callable[[float], typing.Awaitable[None]] = asyncio.sleep) -> None:
        self._transport = transport
        self._policy = _Policy(max_retries, backoff_factor, retry_on_status)
        self._sleep = sleep

    async def handle_async_request(self, request: Request) -> Response:
        p = self._policy
        if request.method not in IDEMPOTENT:
            return await self._transport.handle_async_request(request)
        for attempt in range(1, p.max_retries + 2):
            last = attempt > p.max_retries
            try:
                response = await self._transport.handle_async_request(request)
            except TransportError:
                if last:
                    raise
                await self._sleep(p.delay(attempt, None))
                continue
            if last or response.status_code not in p.retry_on_status:
                return response
            await response.aclose()
            await self._sleep(p.delay(attempt, response))
        raise AssertionError("unreachable")  # pragma: no cover

    async def aclose(self) -> None:
        await self._transport.aclose()
