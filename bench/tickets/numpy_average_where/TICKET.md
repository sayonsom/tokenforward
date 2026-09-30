Add a `where=` parameter to `np.average` and `np.ma.average`, matching the semantics of `np.mean(where=...)`.

1. Signature: `np.average(a, axis=None, weights=None, returned=False, *, keepdims=<no value>, where=<no value>)`. Same for `np.ma.average`. `where` is an array_like of bool, broadcast against `a`; only elements where it is True are included.
2. Without `weights`: result equals `np.mean(a, axis=axis, keepdims=keepdims, where=where)`. With `returned=True`, the second value is the count of included elements (same dtype as the average).
3. With `weights`: excluded elements contribute neither value nor weight. Values at excluded positions (including nan or inf) must not affect the result. With `returned=True`, the second value is the sum of included weights. Existing weights rules still apply (1-D weights along `axis`, shape checks).
4. A slice with no included elements: without weights, the result is nan with a RuntimeWarning (as `np.mean`). With weights, raise the existing `ZeroDivisionError`.
5. Supports int and tuple `axis`, `keepdims`, and broadcasting of `where`. Omitting `where` leaves every existing behaviour and result unchanged.
6. `np.ma.average`: entries that are masked or excluded by `where` are both left out.
7. Update the `__array_function__` dispatcher so `where` takes part in dispatch, as in `np.mean`.
8. Update the type stubs: every `average` overload in `numpy/lib/_function_base_impl.pyi` accepts `where`.
9. Document `where` in both docstrings with `.. versionadded:: 2.5.0`, and add a release note fragment `doc/release/upcoming_changes/<number>.new_feature.rst`.
10. Add tests.

Environment: numpy is not compiled in this checkout; do not try to build it. Run tests with `python run_tests.py <pytest args>`, e.g. `python run_tests.py numpy/lib/tests/test_function_base.py -k average -q`. It overlays your Python and stub changes onto a prebuilt numpy 2.4.6.
