Add `Series.str.truncate` to pandas: shorten strings to a maximum width with a placeholder.

1. New accessor method `Series.str.truncate(width, side="right", placeholder="...")` in `pandas/core/strings/accessor.py`. Strings longer than `width` are cut so the result, including `placeholder`, is exactly `width` characters. Shorter strings are unchanged.
2. `side` is "right" (keep the start), "left" (keep the end) or "middle" (keep both ends, placeholder in the middle; the extra character goes to the start).
3. Raise `ValueError` when `width` is smaller than `len(placeholder)` or `side` is not one of the three values. Raise `TypeError` when `width` is not an int.
4. Missing values stay missing. Works for object dtype and the `str` dtype with both python and pyarrow storage: implement `_str_truncate` in `pandas/core/strings/object_array.py` and in `pandas/core/arrays/_arrow_string_mixins.py`, following how `_str_wrap` / `_str_removeprefix` are done.
5. `Index.str.truncate` works through the same accessor.
6. Docstring in the pandas style (Parameters, Returns, See Also, Examples) with `.. versionadded:: 3.1.0`.
7. Add `Series.str.truncate` to the string methods list in `doc/source/reference/series.rst`, and a whatsnew entry under "Other enhancements" in `doc/source/whatsnew/v3.1.0.rst` (create the file from the v3.0.6 layout if it does not exist).
8. Add tests in `pandas/tests/strings/test_strings.py` covering all three sides, NaN, both string storages, Index, and the errors.

Environment: pandas is not compiled in this checkout; do not try to build it. Run tests with `python run_tests.py <pytest args>`, e.g. `python run_tests.py pandas/tests/strings/test_strings.py -k truncate -q`. It overlays your Python changes onto a prebuilt pandas 3.0.6.
