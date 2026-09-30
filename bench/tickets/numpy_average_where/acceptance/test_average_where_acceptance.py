"""Hidden acceptance tests for numpy_average_where. Identical for every arm. Never shown to the agent.
Run with PYTHONPATH=<overlay> and NP_REPO=<arm checkout>."""
import glob
import os
import re

import numpy as np
import pytest
from numpy.testing import assert_allclose, assert_equal

A = np.array([[1., 2., 3.], [4., 5., 6.]])
W = np.array([[True, False, True], [True, True, False]])
WTS = np.array([[1., 2., 3.], [4., 5., 6.]])
REPO = os.environ.get("NP_REPO", "")


def test_matches_mean_no_axis():
    assert_allclose(np.average(A, where=W), 3.25)
    assert_allclose(np.average(A, where=W), np.mean(A, where=W))


def test_axis0_axis1():
    assert_allclose(np.average(A, axis=0, where=W), [2.5, 5., 3.])
    assert_allclose(np.average(A, axis=1, where=W), [2., 4.5])


def test_axis_tuple_and_keepdims():
    assert_allclose(np.average(A, axis=(0, 1), where=W), 3.25)
    r = np.average(A, axis=1, where=W, keepdims=True)
    assert r.shape == (2, 1)
    assert_allclose(r, [[2.], [4.5]])


def test_where_broadcasts():
    assert_allclose(np.average(A, axis=1, where=[True, False, True]), [2., 5.])


def test_returned_counts_without_weights():
    avg, scl = np.average(A, axis=1, where=W, returned=True)
    assert_allclose(avg, [2., 4.5])
    assert_allclose(scl, [2., 2.])
    assert scl.dtype == avg.dtype


def test_weights_full_shape():
    assert_allclose(np.average(A, weights=WTS, where=W), 51. / 13.)


def test_weights_returned():
    avg, scl = np.average(A, axis=1, weights=WTS, where=W, returned=True)
    assert_allclose(avg, [2.5, 41. / 9.])
    assert_allclose(scl, [4., 9.])


def test_weights_1d_along_axis():
    assert_allclose(np.average(A, axis=1, weights=[1., 2., 3.], where=W), [2.5, 14. / 3.])


def test_excluded_nan_and_inf_ignored():
    a = A.copy()
    a[0, 1] = np.nan
    a[1, 2] = np.inf
    assert_allclose(np.average(a, where=W), 3.25)
    assert_allclose(np.average(a, weights=WTS, where=W), 51. / 13.)


def test_empty_slice_no_weights_is_nan_with_warning():
    w = [[False, False, False], [True, True, True]]
    with pytest.warns(RuntimeWarning):
        r = np.average(A, axis=1, where=w)
    assert np.isnan(r[0]) and r[1] == 5.


def test_empty_slice_with_weights_raises():
    w = [[False, False, False], [True, True, True]]
    with pytest.raises(ZeroDivisionError):
        np.average(A, axis=1, weights=WTS, where=w)


def test_defaults_unchanged():
    assert_equal(np.average(A), 3.5)
    assert_allclose(np.average(A, axis=0, weights=WTS), np.average(A, axis=0, weights=WTS, where=True))
    avg, scl = np.average(A, returned=True)
    assert avg == 3.5 and scl == 6.


def test_where_participates_in_dispatch():
    class Sentinel:
        def __array_function__(self, func, types, args, kwargs):
            return "dispatched"

    assert np.average(A, where=Sentinel()) == "dispatched"


def test_ma_where_and_mask_combined():
    x = np.ma.array(A, mask=[[False, False, False], [False, True, False]])
    assert_allclose(np.ma.average(x, where=W), 8. / 3.)
    assert_allclose(np.ma.average(x, weights=WTS, where=W), 26. / 8.)
    avg, scl = np.ma.average(x, axis=1, where=W, returned=True)
    assert_allclose(avg, [2., 4.])
    assert_allclose(scl, [2., 1.])


def test_ma_defaults_unchanged():
    x = np.ma.array(A, mask=[[False, False, False], [False, True, False]])
    assert_allclose(np.ma.average(x), 16. / 5.)


def test_docstrings():
    for f in (np.average, np.ma.average):
        doc = f.__doc__
        assert re.search(r"^\s*where\s*:", doc, re.M), f
        tail = doc[doc.index("where :"):] if "where :" in doc else doc
        assert ".. versionadded:: 2.5.0" in tail[:1500], f


def test_every_stub_overload_accepts_where():
    src = open(os.path.join(REPO, "numpy", "lib", "_function_base_impl.pyi"), encoding="utf-8").read()
    blocks = re.findall(r"^def average\((.*?)\) ->", src, re.M | re.S)
    assert len(blocks) >= 20
    assert all(re.search(r"\bwhere\s*:", b) for b in blocks), sum(1 for b in blocks if "where" not in b)


def test_release_note_fragment():
    frags = glob.glob(os.path.join(REPO, "doc", "release", "upcoming_changes", "*.new_feature.rst"))
    assert any("average" in open(f, encoding="utf-8").read() and "where" in open(f, encoding="utf-8").read() for f in frags)
