#!/usr/bin/env bash
# TokenForward class setup for macOS / Linux. One command:
#   curl -fsSL https://raw.githubusercontent.com/sayonsom/tokenforward/main/setup.sh | bash
# Options: TFD_DEMO=numpy (default pandas), TFD_WORK=~/tfd
set -euo pipefail
WORK="${TFD_WORK:-$HOME/tfd-class}"
DEMO="${TFD_DEMO:-pandas}"
export PATH="$HOME/.local/bin:$PATH"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Installing $1 ..."; eval "$2"; }; command -v "$1" >/dev/null || { echo "$1 missing: install it and rerun"; exit 1; }; }
need git    "echo 'Install git (xcode-select --install or apt install git)'; false"
need node   "echo 'Install Node LTS from nodejs.org'; false"
need uv     "curl -LsSf https://astral.sh/uv/install.sh | sh"
need claude "curl -fsSL https://claude.ai/install.sh | bash"

echo "== Python tools: graphify, spec-kit"
uv tool install graphifyy --force >/dev/null
uv tool install specify-cli --force >/dev/null

echo "== TokenForward source"
mkdir -p "$WORK"
if [ -d "$WORK/tokenforward" ]; then git -C "$WORK/tokenforward" pull -q; else git clone -q https://github.com/sayonsom/tokenforward.git "$WORK/tokenforward"; fi

uv run --python 3.12 --no-project python "$WORK/tokenforward/scripts/class_setup.py" --work "$WORK" --demo "$DEMO"
