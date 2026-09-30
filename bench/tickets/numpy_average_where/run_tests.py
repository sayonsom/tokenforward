#!/usr/bin/env python3
"""numpy is not compiled in this checkout. This copies a prebuilt numpy __NP_VERSION__ into .numpy-overlay/,
overlays every Python/stub file you changed or added under numpy/, then runs pytest there.
Works on Windows, macOS and Linux.

Usage: python run_tests.py numpy/lib/tests/test_function_base.py -k average -q
       python run_tests.py --sync-only
"""
import os
import shutil
import subprocess
import sys

WHEEL_SITE = r"__WHEEL_SITE__"
PYTHON = r"__PYTHON__"
ROOT = os.path.dirname(os.path.abspath(__file__))
OV = os.path.join(ROOT, ".numpy-overlay")


def git(*args):
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True)
    return [l for l in out.stdout.splitlines() if l.strip()]


def _rm_readonly(func, path, _):
    os.chmod(path, 0o700)
    func(path)


def sync():
    if os.path.exists(OV):
        shutil.rmtree(OV, onerror=_rm_readonly)
    os.makedirs(OV)
    shutil.copytree(os.path.join(WHEEL_SITE, "numpy"), os.path.join(OV, "numpy"))
    libs = os.path.join(WHEEL_SITE, "numpy.libs")
    if os.path.isdir(libs):
        shutil.copytree(libs, os.path.join(OV, "numpy.libs"))
    changed = set(git("diff", "--name-only", "bench-base", "--", "numpy"))
    changed |= set(git("ls-files", "-o", "--exclude-standard", "--", "numpy"))
    for f in sorted(changed):
        src = os.path.join(ROOT, f)
        if f.endswith((".py", ".pyi")) and os.path.isfile(src):
            dst = os.path.join(OV, f)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)


if __name__ == "__main__":
    sync()
    if sys.argv[1:] == ["--sync-only"]:
        sys.exit(0)
    sys.exit(subprocess.call([PYTHON, "-m", "pytest", "-p", "no:cacheprovider", *sys.argv[1:]], cwd=OV))
