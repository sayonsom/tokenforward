#!/usr/bin/env bash
# numpy is not compiled in this checkout. This copies a prebuilt numpy __NP_VERSION__ into .numpy-overlay/,
# overlays every Python/stub file you changed or added under numpy/, then runs pytest there.
# Usage: ./run_tests.sh numpy/lib/tests/test_function_base.py -k average -q
#        ./run_tests.sh --sync-only
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OV="$ROOT/.numpy-overlay"
rm -rf "$OV" && mkdir -p "$OV"
cp -r "__WHEEL_SITE__/numpy" "$OV/numpy"
[ -d "__WHEEL_SITE__/numpy.libs" ] && cp -r "__WHEEL_SITE__/numpy.libs" "$OV/numpy.libs"
cd "$ROOT"
{ git diff --name-only bench-base -- numpy; git ls-files -o --exclude-standard -- numpy; } \
  | { grep -E '\.(py|pyi)$' || true; } | sort -u | while read -r f; do
    if [ -f "$f" ]; then mkdir -p "$OV/$(dirname "$f")"; cp "$f" "$OV/$f"; fi
  done
[ "${1:-}" = "--sync-only" ] && exit 0
cd "$OV"
exec "__PYTHON__" -m pytest -p no:cacheprovider "$@"
