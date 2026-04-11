#!/usr/bin/env bash
# devsper installer
# Usage: curl -fsSL https://devsper.com/install.sh | bash
set -euo pipefail

BOLD='\033[1m'
DIM='\033[2m'
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
RESET='\033[0m'

info()  { printf "${DIM}  %s${RESET}\n" "$*"; }
ok()    { printf "${GREEN}  ✓ %s${RESET}\n" "$*"; }
warn()  { printf "${YELLOW}  ⚠ %s${RESET}\n" "$*"; }
die()   { printf "${RED}  ✗ %s${RESET}\n" "$*"; exit 1; }

printf "\n${BOLD}${CYAN}devsper${RESET}  installer\n\n"

# ── Require Python 3.12+ ─────────────────────────────────────────────────────
PY=$(python3 --version 2>/dev/null | awk '{print $2}') || true
if [[ -z "$PY" ]]; then
  die "python3 not found. Install Python 3.12+ first."
fi
PY_MAJOR=$(echo "$PY" | cut -d. -f1)
PY_MINOR=$(echo "$PY" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 12 ) ]]; then
  die "Python $PY found but devsper requires 3.12+."
fi
info "Python $PY"

# ── Ensure uv ────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  info "installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # shellcheck disable=SC1090
  source "$HOME/.cargo/env" 2>/dev/null || true
  export PATH="$HOME/.local/bin:$PATH"
fi
ok "uv $(uv --version 2>/dev/null | head -1)"

# ── Install devsper ──────────────────────────────────────────────────────────
info "installing devsper..."
uv tool install devsper
ok "devsper installed"

# ── Inject trulens-core (conflicts with rich>=14 — override required) ─────────
info "adding TruLens observability..."
OVERRIDE=$(mktemp)
echo "rich>=14.3.3" > "$OVERRIDE"
if uv tool install devsper --with "trulens-core>=1.0" --override "$OVERRIDE" 2>/dev/null; then
  ok "trulens-core added (TruLens observability enabled)"
else
  warn "trulens-core skipped (rich pin conflict). Run manually: pip install trulens-core"
fi
rm -f "$OVERRIDE"

# ── macOS: pre-compile Swift dictation helper ─────────────────────────────────
if [[ "$(uname)" == "Darwin" ]] && command -v swiftc &>/dev/null; then
  info "compiling macOS voice helper..."
  SWIFT_SRC=$(python3 -c "
import importlib.util, pathlib
spec = importlib.util.find_spec('devsper.workspace.voice')
if spec: print(pathlib.Path(spec.origin).parent / 'devsper_dictation.swift')
" 2>/dev/null)
  BIN_DIR="$HOME/.local/share/devsper/bin"
  BIN="$BIN_DIR/devsper-dictation"
  if [[ -n "$SWIFT_SRC" && -f "$SWIFT_SRC" && ! -f "$BIN" ]]; then
    mkdir -p "$BIN_DIR"
    if swiftc \
        -framework Foundation -framework Speech -framework AVFoundation \
        -O "$SWIFT_SRC" -o "$BIN" 2>/dev/null; then
      ok "voice helper compiled"
    else
      warn "voice helper compile failed — will retry on first use"
    fi
  elif [[ -f "$BIN" ]]; then
    ok "voice helper already compiled"
  fi
fi

# ── PATH hint ────────────────────────────────────────────────────────────────
UV_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$UV_BIN:"* ]]; then
  warn "add to your shell profile: export PATH=\"$UV_BIN:\$PATH\""
fi

printf "\n${BOLD}${GREEN}done.${RESET}  run ${BOLD}devsper${RESET} in any project directory.\n\n"
