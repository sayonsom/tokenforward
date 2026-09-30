Add retry support to httpx as a new public transport wrapper.

- `httpx.RetryTransport(transport, *, max_retries=3, backoff_factor=0.5, retry_on_status=(429, 500, 502, 503, 504), sleep=time.sleep)` wraps any `httpx.BaseTransport`.
- `httpx.AsyncRetryTransport(transport, *, ...same..., sleep=asyncio.sleep)` wraps any `httpx.AsyncBaseTransport`; `sleep` is awaited.
- Retry when the wrapped transport returns a status in `retry_on_status`, or raises `httpx.TransportError`.
- Only idempotent methods are retried: GET, HEAD, OPTIONS, PUT, DELETE, TRACE. Other methods are sent once.
- Delay before retry n (n = 1, 2, ...) is `backoff_factor * 2 ** (n - 1)`. If the response has a `Retry-After` header with integer seconds, use that value instead.
- When retries are exhausted, return the last response, or re-raise the last exception.
- Close any response that is discarded before retrying.
- Export both classes from the top-level `httpx` package and add them to `__all__`.
- Add tests.
