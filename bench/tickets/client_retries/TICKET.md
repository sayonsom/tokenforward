Add first-class retry support to the httpx clients.

1. New public config class `httpx.Retry`, defined in `httpx/_config.py`:
   `Retry(total=3, *, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET", "HEAD", "OPTIONS", "PUT", "DELETE", "TRACE"), respect_retry_after=True)`.
   - `total` is the maximum number of retries. `Retry(0)` disables retries.
   - `backoff_for(attempt: int, response: httpx.Response | None = None) -> float` returns `backoff_factor * 2 ** (attempt - 1)` for retry number `attempt` (1-based). If `respect_retry_after` is true and the response has a `Retry-After` header with integer seconds, return that value instead.
   - Instances compare equal when all fields are equal, and have a readable `repr`.
2. `httpx.Client(retries=...)` and `httpx.AsyncClient(retries=...)` accept an `int` (shorthand for `Retry(total=n)`) or a `Retry`. Default is `0`, so existing behaviour does not change. Expose it as a `client.retries` property that returns a `Retry` and can be set.
3. Per-request override: `request.extensions["retries"]` (an `int` or `Retry`) takes precedence over the client setting, e.g. `client.get(url, extensions={"retries": 0})`.
4. Retries happen per hop inside the client's send path. Each redirect hop is retried independently. Response event hooks and auth flows see only the final response of each hop, never the discarded attempts.
5. Retry when the method is in `allowed_methods` and either the status is in `status_forcelist` or the transport raises `httpx.TransportError`. Sleep `backoff_for(...)` seconds between attempts. The async client must sleep in a way that works on both asyncio and trio. Close discarded responses.
6. When retries are exhausted on a status, return the last response. When exhausted on a transport error, raise a new `httpx.RetryError` (subclass of `httpx.RequestError`) with attributes `last_exception` and `attempts` (total attempts made), chained from the last exception. Add it to the exception hierarchy docstring in `httpx/_exceptions.py`.
7. Every response returned by the client has `response.extensions["retries"]` set to the number of retries performed for that hop (0 if none).
8. Export `Retry` and `RetryError` from the top-level `httpx` package.
9. Add tests, and a docs page `docs/advanced/retries.md` linked from the mkdocs nav.
